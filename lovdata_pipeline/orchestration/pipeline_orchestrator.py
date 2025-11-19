"""Pipeline orchestrator for coordinating the complete ETL pipeline.

Responsible for orchestrating the entire pipeline execution.
Single Responsibility: Coordinate sync -> identify -> process -> cleanup stages.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from lovdata_pipeline.domain.services.file_processing_service import (
    FileInfo,
    FileProcessingService,
)
from lovdata_pipeline.domain.vector_store import VectorStoreRepository
from lovdata_pipeline.lovlig import Lovlig
from lovdata_pipeline.progress import NoOpProgressTracker, ProgressTracker
from lovdata_pipeline.state import ProcessingState

logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    """Configuration for pipeline execution."""

    data_dir: Path
    dataset_filter: str
    force: bool = False


@dataclass
class PipelineResult:
    """Result of pipeline execution."""

    processed: int
    failed: int
    removed: int


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
        to_process, removed = self._identify_files(lovlig, state, config.force, progress_tracker)

        # Stage 3: Process files
        processed, failed = self._process_files(to_process, state, progress_tracker)

        # Stage 4: Clean up removed files
        removed_count = self._cleanup_removed_files(removed, state, progress_tracker)

        # Show summary
        summary = state.stats()
        summary["removed"] = removed_count
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
            f"Sync stats - Added: {stats['added']}, "
            f"Modified: {stats['modified']}, Removed: {stats['removed']}"
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
    ) -> tuple[list[FileInfo], list[dict]]:
        """Identify files to process and removed files."""
        progress_tracker.start_stage("identify", "Identifying files")

        changed = lovlig.get_changed_files()
        removed = lovlig.get_removed_files()

        # Filter already processed (unless force)
        to_process = []
        if force:
            to_process = [self._convert_to_file_info(f) for f in changed]
        else:
            for f in changed:
                if not state.is_processed(f["doc_id"], f["hash"]):
                    to_process.append(self._convert_to_file_info(f))

        logger.debug(
            f"Processing {len(to_process)} files, skipped {len(changed) - len(to_process)}"
        )
        progress_tracker.end_stage("identify")

        return to_process, removed

    def _convert_to_file_info(self, file_dict: dict) -> FileInfo:
        """Convert lovlig file dict to FileInfo."""
        return FileInfo(
            doc_id=file_dict["doc_id"],
            path=file_dict["path"],
            dataset=file_dict["dataset"],
            hash=file_dict["hash"],
        )

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
                    # Generate vector IDs for state tracking
                    vector_ids = [
                        f"{file_info.doc_id}_chunk_{i}" for i in range(result.chunk_count)
                    ]
                    state.mark_processed(file_info.doc_id, file_info.hash, vector_ids)
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
        removed: list[dict],
        state: ProcessingState,
        progress_tracker: ProgressTracker,
    ) -> int:
        """Clean up removed files from vector store and state."""
        if not removed:
            return 0

        progress_tracker.start_stage("cleanup", "Cleaning up removed documents")
        removed_count = 0

        for r in removed:
            doc_id = r["doc_id"]
            vectors = state.get_vectors(doc_id)

            if vectors:
                self._vector_store.delete_by_document_id(vectors)
                logger.debug(f"Deleted {len(vectors)} vectors for {doc_id}")
                removed_count += 1
            else:
                progress_tracker.log_warning(
                    f"Document {doc_id} removed but not in state. "
                    "Ghost vectors may remain in vector store."
                )

            state.remove(doc_id)

        state.save()
        progress_tracker.end_stage("cleanup")

        return removed_count
