"""File processing service for legal documents.

Responsible for coordinating the complete processing of a single file.
Single Responsibility: Orchestrate chunk -> embed -> index for one file.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from lovdata_pipeline.domain.services.chunking_service import ChunkingService
from lovdata_pipeline.domain.services.embedding_service import EmbeddingService
from lovdata_pipeline.domain.vector_store import VectorStoreRepository

logger = logging.getLogger(__name__)


@dataclass
class FileProcessingResult:
    """Result of processing a single file."""

    success: bool
    chunk_count: int
    error_message: str | None = None


@dataclass
class FileInfo:
    """Information about a file to process."""

    doc_id: str
    path: Path
    dataset: str
    hash: str


class FileProcessingService:
    """Service for processing individual legal document files.

    Single Responsibility: Coordinate the complete processing pipeline
    for a single file (chunk, embed, index).
    """

    def __init__(
        self,
        chunking_service: ChunkingService,
        embedding_service: EmbeddingService,
        vector_store: VectorStoreRepository,
    ):
        """Initialize file processing service.

        Args:
            chunking_service: Service for chunking XML files
            embedding_service: Service for generating embeddings
            vector_store: Repository for storing vectors
        """
        self._chunking_service = chunking_service
        self._embedding_service = embedding_service
        self._vector_store = vector_store

    def process_file(
        self,
        file_info: FileInfo,
        progress_callback: Callable[[int, int], None] | None = None,
        warning_callback: Callable[[str], None] | None = None,
    ) -> FileProcessingResult:
        """Process a single file through the complete pipeline.

        On any error, we delete ALL chunks for this document (by doc_id metadata filter)
        and the orchestrator will retry processing. This is simpler than tracking partial
        state and we can afford to re-embed a failing file.

        Args:
            file_info: Information about the file to process
            progress_callback: Optional callback(current, total) for embedding progress
            warning_callback: Optional callback(message) for warnings

        Returns:
            FileProcessingResult with success status, chunk count, and optional error
        """
        try:
            # 1. Validate file exists
            if not file_info.path.exists():
                return FileProcessingResult(
                    success=False,
                    chunk_count=0,
                    error_message=f"File not found: {file_info.path}",
                )

            # 2. Chunk XML file directly
            all_chunks = self._chunking_service.chunk_file(
                file_info.path,
                file_info.doc_id,
                file_info.dataset,
                file_info.hash,
            )

            if not all_chunks:
                error_msg = f"No chunks generated from {file_info.doc_id}"
                if warning_callback:
                    warning_callback(error_msg)
                return FileProcessingResult(success=False, chunk_count=0, error_message=error_msg)

            logger.debug(f"  Chunked: {len(all_chunks)} chunks")

            # 3. Embed chunks
            enriched = self._embedding_service.embed_chunks(
                all_chunks,
                progress_callback=progress_callback,
            )
            logger.debug(f"  Embedded: {len(enriched)} chunks")

            # 4. Generate vector IDs
            vector_ids = [f"{file_info.doc_id}_chunk_{i}" for i in range(len(enriched))]

            # Set IDs on enriched chunks
            for chunk, vid in zip(enriched, vector_ids, strict=True):
                chunk.chunk_id = vid

            # 5. Index in vector store (upsert = replace old if exists)
            self._vector_store.upsert_chunks(enriched)
            logger.debug(f"  Indexed: {len(vector_ids)} vectors")

            return FileProcessingResult(
                success=True,
                chunk_count=len(all_chunks),
            )

        except Exception as e:
            logger.debug(f"  Failed: {e}")

            # Clean up ALL chunks for this document (simpler than tracking partial state)
            try:
                deleted = self._vector_store.delete_by_document_id(file_info.doc_id)
                if deleted > 0:
                    logger.debug(f"  Cleaned up {deleted} chunks for {file_info.doc_id}")
            except Exception as cleanup_error:
                logger.debug(f"  Failed to clean up chunks: {cleanup_error}")

            return FileProcessingResult(
                success=False,
                chunk_count=0,
                error_message=str(e),
            )
