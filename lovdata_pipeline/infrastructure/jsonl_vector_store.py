"""JSONL file-based vector store implementation.

Stores chunks as JSONL files, one file per document, named by source file hash.
This provides a simple, portable, and inspectable storage format.
"""

import json
import logging
from pathlib import Path

from lovdata_pipeline.domain.models import EnrichedChunk

logger = logging.getLogger(__name__)


class JsonlVectorStoreRepository:
    """JSONL file-based implementation of VectorStoreRepository.

    Stores each document's chunks in a separate JSONL file named by source hash.
    Format: {hash}.jsonl containing one JSON object per line (one per chunk).

    File naming convention:
        {source_hash}.jsonl - e.g., "abc123def456.jsonl"

    This enables:
    - Easy inspection and debugging
    - Simple backup and version control
    - Portability across systems
    - Direct mapping from document to chunks via hash
    """

    def __init__(self, storage_dir: Path):
        """Initialize JSONL vector store.

        Args:
            storage_dir: Directory to store JSONL files
        """
        self._storage_dir = Path(storage_dir)
        self._storage_dir.mkdir(parents=True, exist_ok=True)

    def upsert_chunks(self, chunks: list[EnrichedChunk]) -> None:
        """Store or update chunks in JSONL files.

        Groups chunks by source_hash and writes one file per document.

        Args:
            chunks: List of enriched chunks with embeddings to store

        Raises:
            OSError: If file write operation fails
        """
        if not chunks:
            return

        # Group chunks by source_hash
        chunks_by_hash: dict[str, list[EnrichedChunk]] = {}
        for chunk in chunks:
            source_hash = chunk.source_hash or "unknown"
            if source_hash not in chunks_by_hash:
                chunks_by_hash[source_hash] = []
            chunks_by_hash[source_hash].append(chunk)

        # Write each group to its own JSONL file
        for source_hash, chunk_group in chunks_by_hash.items():
            file_path = self._storage_dir / f"{source_hash}.jsonl"

            # Load existing chunks from file (if exists)
            existing_chunks = self._load_chunks_from_file(file_path)

            # Create a dict for quick lookup by chunk_id
            chunk_dict = {c.chunk_id: c for c in existing_chunks}

            # Update with new chunks (upsert)
            for chunk in chunk_group:
                chunk_dict[chunk.chunk_id] = chunk

            # Write all chunks back to file
            self._write_chunks_to_file(file_path, list(chunk_dict.values()))

            logger.debug(f"Wrote {len(chunk_group)} chunks to {file_path.name}")

    def delete_by_document_id(self, doc_id: str) -> int:
        """Delete all chunks for a document.

        Since we store by hash, we need to scan files to find chunks with this doc_id.

        Args:
            doc_id: Document ID to delete all chunks for

        Returns:
            Number of chunks deleted

        Raises:
            OSError: If file operations fail
        """
        if not doc_id:
            return 0

        deleted_count = 0

        # Scan all JSONL files
        for jsonl_file in self._storage_dir.glob("*.jsonl"):
            chunks = self._load_chunks_from_file(jsonl_file)

            # Filter out chunks matching this doc_id
            remaining_chunks = [c for c in chunks if c.document_id != doc_id]
            chunks_deleted = len(chunks) - len(remaining_chunks)

            if chunks_deleted > 0:
                if remaining_chunks:
                    # Write back remaining chunks
                    self._write_chunks_to_file(jsonl_file, remaining_chunks)
                else:
                    # No chunks left, delete the file
                    jsonl_file.unlink()
                    logger.debug(f"Deleted empty file: {jsonl_file.name}")

                deleted_count += chunks_deleted
                logger.debug(f"Deleted {chunks_deleted} chunks from {jsonl_file.name}")

        return deleted_count

    def count(self) -> int:
        """Get total count of chunks in all JSONL files.

        Returns:
            Total number of chunks stored

        Raises:
            OSError: If file read operations fail
        """
        total = 0
        for jsonl_file in self._storage_dir.glob("*.jsonl"):
            with open(jsonl_file) as f:
                total += sum(1 for _ in f)
        return total

    def get_chunks_by_hash(self, source_hash: str) -> list[EnrichedChunk]:
        """Get all chunks for a specific source file hash.

        Args:
            source_hash: Source file hash to retrieve chunks for

        Returns:
            List of chunks from that file

        Raises:
            OSError: If file read operation fails
        """
        file_path = self._storage_dir / f"{source_hash}.jsonl"
        if not file_path.exists():
            return []
        return self._load_chunks_from_file(file_path)

    def get_chunks_by_document_id(self, doc_id: str) -> list[EnrichedChunk]:
        """Get all chunks for a specific document ID.

        Args:
            doc_id: Document ID to retrieve chunks for

        Returns:
            List of chunks for that document

        Raises:
            OSError: If file read operations fail
        """
        all_chunks = []
        for jsonl_file in self._storage_dir.glob("*.jsonl"):
            chunks = self._load_chunks_from_file(jsonl_file)
            matching_chunks = [c for c in chunks if c.document_id == doc_id]
            all_chunks.extend(matching_chunks)
        return all_chunks

    def list_hashes(self) -> list[str]:
        """List all source hashes that have stored chunks.

        Returns:
            List of source file hashes
        """
        return [f.stem for f in self._storage_dir.glob("*.jsonl")]

    def _load_chunks_from_file(self, file_path: Path) -> list[EnrichedChunk]:
        """Load chunks from a JSONL file.

        Args:
            file_path: Path to JSONL file

        Returns:
            List of EnrichedChunk objects

        Raises:
            OSError: If file read fails
            json.JSONDecodeError: If JSON parsing fails
        """
        if not file_path.exists():
            return []

        chunks = []
        with open(file_path) as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    chunks.append(EnrichedChunk(**data))
                except (json.JSONDecodeError, TypeError, ValueError) as e:
                    logger.warning(f"Failed to parse line {line_num} in {file_path.name}: {e}")
                    continue

        return chunks

    def _write_chunks_to_file(self, file_path: Path, chunks: list[EnrichedChunk]) -> None:
        """Write chunks to a JSONL file (atomic write).

        Args:
            file_path: Path to JSONL file
            chunks: List of chunks to write

        Raises:
            OSError: If file write fails
        """
        # Atomic write: write to temp file, then rename
        tmp_path = file_path.with_suffix(".tmp")

        with open(tmp_path, "w") as f:
            for chunk in chunks:
                # Convert to dict for JSON serialization
                chunk_dict = chunk.model_dump()
                f.write(json.dumps(chunk_dict) + "\n")

        # Atomic rename
        tmp_path.replace(file_path)
