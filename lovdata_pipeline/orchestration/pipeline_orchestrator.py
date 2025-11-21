"""Pipeline orchestrator for coordinating the complete ETL pipeline.

Responsible for orchestrating the entire pipeline execution.
Single Responsibility: Coordinate sync -> identify -> process -> cleanup stages.
"""

import logging
from pathlib import Path

import chromadb
from openai import OpenAI

from lovdata_pipeline.domain.models import FileInfo, PipelineConfig, PipelineResult
from lovdata_pipeline.domain.services.chunking_service import ChunkingService
from lovdata_pipeline.domain.services.embedding_service import EmbeddingService
from lovdata_pipeline.domain.services.file_processing_service import FileProcessingService
from lovdata_pipeline.domain.vector_store import VectorStoreRepository
from lovdata_pipeline.infrastructure.chroma_vector_store import ChromaVectorStoreRepository
from lovdata_pipeline.infrastructure.jsonl_vector_store import JsonlVectorStoreRepository
from lovdata_pipeline.infrastructure.openai_embedding_provider import OpenAIEmbeddingProvider
from lovdata_pipeline.lovlig import Lovlig
from lovdata_pipeline.progress import NoOpProgressTracker, ProgressTracker
from lovdata_pipeline.state import ProcessingState

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    """Orchestrator for the complete pipeline execution.

    Single Responsibility: Coordinate the high-level pipeline stages
    (sync, identify, process, cleanup) using injected services.
    """

    def __init__(
        self,
        file_processor: FileProcessingService,
        vector_store: VectorStoreRepository,
    ):
        """Initialize pipeline orchestrator.

        Args:
            file_processor: Service for processing individual files
            vector_store: Repository for vector storage operations
        """
        self._file_processor = file_processor
        self._vector_store = vector_store

    @classmethod
    def create(
        cls,
        openai_api_key: str,
        embedding_model: str,
        chunk_max_tokens: int,
        storage_type: str = "chroma",
        chroma_path: str = "./data/chroma",
        data_dir: str = "./data",
        chunk_target_tokens: int = 768,
        chunk_min_tokens: int = 300,
        chunk_overlap_ratio: float = 0.15,
        embedding_dimensions: int | None = 1024,
    ) -> "PipelineOrchestrator":
        """Factory method to create a fully configured pipeline orchestrator.

        Args:
            openai_api_key: OpenAI API key
            embedding_model: Model to use for embeddings
            chunk_max_tokens: Maximum tokens per chunk
            storage_type: Storage type ('chroma' or 'jsonl')
            chroma_path: Path to ChromaDB storage
            data_dir: Data directory for JSONL storage
            chunk_target_tokens: Target tokens per chunk
            chunk_min_tokens: Minimum tokens per chunk
            chunk_overlap_ratio: Overlap ratio between chunks
            embedding_dimensions: Embedding dimensions (1024 for storage efficiency)

        Returns:
            Configured PipelineOrchestrator instance
        """
        # Create OpenAI client and embedding provider
        openai_client = OpenAI(api_key=openai_api_key)
        embedding_provider = OpenAIEmbeddingProvider(
            openai_client, embedding_model, dimensions=embedding_dimensions
        )

        # Initialize vector store based on storage type
        if storage_type == "jsonl":
            jsonl_path = Path(data_dir) / "jsonl_chunks"
            vector_store: VectorStoreRepository = JsonlVectorStoreRepository(jsonl_path)
            logger.info(f"Using JSONL storage at: {jsonl_path}")
        else:  # chroma (default)
            chroma_client = chromadb.PersistentClient(path=chroma_path)
            collection = chroma_client.get_or_create_collection(
                name="legal_docs",
                metadata={"description": "Norwegian legal documents"},
            )
            vector_store = ChromaVectorStoreRepository(collection)
            logger.info(f"Using ChromaDB storage at: {chroma_path}")

        # Create domain services
        chunking_service = ChunkingService(
            target_tokens=chunk_target_tokens,
            max_tokens=chunk_max_tokens,
            min_tokens=chunk_min_tokens,
            overlap_ratio=chunk_overlap_ratio,
        )
        embedding_service = EmbeddingService(provider=embedding_provider, batch_size=100)
        file_processor = FileProcessingService(
            chunking_service=chunking_service,
            embedding_service=embedding_service,
            vector_store=vector_store,
        )

        return cls(file_processor=file_processor, vector_store=vector_store)

    def run(
        self,
        config: PipelineConfig,
        progress_tracker: ProgressTracker | None = None,
    ) -> PipelineResult:
        """Run the complete pipeline.

        Args:
            config: Pipeline configuration
            progress_tracker: Optional progress tracker. Uses NoOp if not provided.

        Returns:
            PipelineResult with counts of processed, failed, and removed documents

        Raises:
            RuntimeError: If vector store connection fails or lovlig state not created
        """
        # Use NoOp tracker if none provided
        if progress_tracker is None:
            progress_tracker = NoOpProgressTracker()

        # Initialize dependencies
        lovlig = self._create_lovlig_client(config)
        state = ProcessingState(config.data_dir / "pipeline_state.json")

        # Validate vector store connection
        self._validate_vector_store()

        # Stage 1: Sync datasets
        self._sync_datasets(lovlig, config.force, progress_tracker)

        # Validate lovlig state was created
        self._validate_lovlig_state(lovlig)

        # Stage 2: Identify files to process
        to_process, removed = self._identify_files(
            lovlig, state, config.force, progress_tracker, config.limit
        )

        # Stage 3: Process files
        processed, failed = self._process_files(to_process, state, progress_tracker)

        # Stage 4: Clean up removed files
        removed_count = self._cleanup_removed_files(removed, state, progress_tracker)

        # Show summary (use counts from this run, not cumulative state)
        summary = {
            "processed": processed,
            "failed": failed,
            "removed": removed_count,
        }
        progress_tracker.show_summary(summary)

        return PipelineResult(
            processed=processed,
            failed=failed,
            removed=removed_count,
        )

    def _create_lovlig_client(self, config: PipelineConfig) -> Lovlig:
        """Create and configure lovlig client."""
        return Lovlig(
            dataset_filter=config.dataset_filter,
            raw_dir=config.data_dir / "raw",
            extracted_dir=config.data_dir / "extracted",
            state_file=config.data_dir / "state.json",
        )

    def _validate_vector_store(self) -> None:
        """Validate that vector store is accessible."""
        try:
            self._vector_store.count()
        except Exception as e:
            raise RuntimeError(f"Vector store connection failed: {e}") from e

    def _sync_datasets(
        self,
        lovlig: Lovlig,
        force: bool,
        progress_tracker: ProgressTracker,
    ) -> None:
        """Sync datasets from Lovdata."""
        progress_tracker.start_stage("sync", "Syncing datasets")
        stats = lovlig.sync(force=force)
        logger.debug(
            f"Sync stats - Added: {stats.added}, "
            f"Modified: {stats.modified}, Removed: {stats.removed}"
        )
        progress_tracker.end_stage("sync")

    def _validate_lovlig_state(self, lovlig: Lovlig) -> None:
        """Validate that lovlig state file was created."""
        if not lovlig.state_file.exists():
            raise RuntimeError(
                f"Lovlig state file not created at {lovlig.state_file}. "
                "Sync may have failed. Check network connection and permissions."
            )

    def _identify_files(
        self,
        lovlig: Lovlig,
        state: ProcessingState,
        force: bool,
        progress_tracker: ProgressTracker,
        limit: int | None = None,
    ) -> tuple[list[FileInfo], list[dict]]:
        """Identify files to process and removed files.

        Critical: This method uses our pipeline_state.json as the source of truth,
        NOT lovlig's state.json. This prevents data loss if lovlig's state is
        updated between pipeline runs.

        Strategy:
        1. Get changed files from lovlig (based on lovlig's state.json)
        2. Filter using OUR pipeline_state.json to determine what needs processing
        3. Only skip files that are in OUR state with matching hash

        Args:
            lovlig: Lovlig client instance
            state: Processing state tracker (pipeline_state.json)
            force: Whether to force reprocessing
            progress_tracker: Progress tracker instance
            limit: Optional limit on number of files to process

        Returns:
            Tuple of (files to process, removed files)
        """
        progress_tracker.start_stage("identify", "Identifying files")

        changed = lovlig.get_changed_files()
        removed = lovlig.get_removed_files()

        to_process = []
        if force:
            # When forcing, process ALL files (not just changed)
            all_files = lovlig.get_all_files()
            to_process = [
                FileInfo(doc_id=f.doc_id, path=f.path, dataset=f.dataset, hash=f.hash)
                for f in all_files
            ]
            total_available = len(all_files)
        else:
            # Use OUR pipeline_state.json to filter - this is the critical fix
            # Only skip if WE have processed it with the same hash
            total_available = len(changed)
            for f in changed:
                if not state.is_processed(f.doc_id, f.hash):
                    to_process.append(
                        FileInfo(doc_id=f.doc_id, path=f.path, dataset=f.dataset, hash=f.hash)
                    )

        # Apply limit if specified
        if limit is not None and limit > 0:
            original_count = len(to_process)
            to_process = to_process[:limit]
            logger.info(f"Limit applied: processing {len(to_process)} of {original_count} files")

        # Calculate skipped count correctly
        skipped = total_available - len(to_process)
        logger.debug(f"Processing {len(to_process)} files, skipped {skipped}")
        progress_tracker.end_stage("identify")

        return to_process, removed

    def _process_files(
        self,
        to_process: list[FileInfo],
        state: ProcessingState,
        progress_tracker: ProgressTracker,
    ) -> tuple[int, int]:
        """Process all files."""
        progress_tracker.start_stage("process", "Processing documents")
        processed = 0
        failed = 0

        if to_process:
            progress_tracker.start_file_processing(len(to_process))

            for idx, file_info in enumerate(to_process, 1):
                # Update progress bar with current file
                progress_tracker.update_file(file_info.doc_id, idx - 1, len(to_process))

                # Create embedding progress callback
                def embedding_progress(current: int, total: int):
                    progress_tracker.update_embedding(current, total)

                # Start embedding tracking
                progress_tracker.start_embedding(0)  # Will be updated by callback

                # Process the file
                result = self._file_processor.process_file(
                    file_info,
                    progress_callback=embedding_progress,
                    warning_callback=progress_tracker.log_warning,
                )

                # End embedding tracking
                progress_tracker.end_embedding()

                # Update state based on result
                if result.success:
                    state.mark_processed(file_info.doc_id, file_info.hash)
                    state.save()
                    processed += 1
                    progress_tracker.log_success(file_info.doc_id, result.chunk_count)
                else:
                    state.mark_failed(
                        file_info.doc_id,
                        file_info.hash,
                        result.error_message or "Unknown error",
                    )
                    state.save()
                    failed += 1
                    progress_tracker.log_error(
                        file_info.doc_id, result.error_message or "Unknown error"
                    )

            # Complete the progress bar
            progress_tracker.update_file("", len(to_process), len(to_process))
            progress_tracker.end_file_processing()

        progress_tracker.end_stage("process")
        return processed, failed

    def _cleanup_removed_files(
        self,
        removed: list,
        state: ProcessingState,
        progress_tracker: ProgressTracker,
    ) -> int:
        """Clean up removed files from vector store and state."""
        if not removed:
            return 0

        progress_tracker.start_stage("cleanup", "Cleaning up removed documents")
        removed_count = 0

        for r in removed:
            doc_id = r.doc_id

            # Delete all chunks for this document using metadata filter
            try:
                deleted = self._vector_store.delete_by_document_id(doc_id)
                if deleted > 0:
                    logger.debug(f"Deleted {deleted} chunks for {doc_id}")
                    removed_count += 1
                else:
                    # Document was tracked but had no vectors (maybe never fully processed)
                    logger.debug(f"No chunks found for {doc_id}")
            except Exception as e:
                progress_tracker.log_warning(f"Failed to delete chunks for {doc_id}: {e}")

            state.remove(doc_id)

        state.save()
        progress_tracker.end_stage("cleanup")

        return removed_count
