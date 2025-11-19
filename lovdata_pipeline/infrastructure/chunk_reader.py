"""Reader for extracting chunks from JSONL files.

This module provides functionality to read chunks from the legal_chunks.jsonl
file by document ID, supporting memory-efficient streaming.
"""

from collections.abc import Iterator
from pathlib import Path

import jsonlines

from lovdata_pipeline.domain.models import ChunkMetadata, EnrichedChunk


class ChunkReader:
    """Read chunks from JSONL file by document ID.

    Provides methods to read chunks for specific documents or stream
    all chunks from the file. Returns ChunkMetadata or EnrichedChunk
    based on whether chunks have embeddings.

    Args:
        chunks_file: Path to the JSONL file containing chunks
    """

    def __init__(self, chunks_file: Path):
        """Initialize the chunk reader."""
        self.chunks_file = chunks_file


class EnrichedChunkReader(ChunkReader):
    """Reader specifically for enriched chunks with embeddings.

    This reader enforces that all chunks must have embeddings and will
    raise an error if encountering chunks without them. Use this when
    reading from embedded_chunks.jsonl or other files that are known
    to contain only enriched chunks.

    Args:
        chunks_file: Path to the JSONL file containing enriched chunks
    """

    def read_chunks(self, file_paths: set[str] | None = None) -> Iterator[EnrichedChunk]:
        """Read enriched chunks, optionally filtered by file paths.

        Args:
            file_paths: Optional set of file paths to filter by.
                       If provided, only chunks from these files are returned.

        Yields:
            EnrichedChunk object for each matching chunk

        Raises:
            ValueError: If a chunk is missing required embedding data
        """
        if not self.chunks_file.exists():
            return

        with jsonlines.open(self.chunks_file) as reader:
            for chunk_dict in reader:
                # If filtering by file paths, check if this chunk matches
                if file_paths is not None:
                    # Reconstruct the likely file path from chunk data
                    dataset_name = chunk_dict.get("dataset_name", "")
                    document_id = chunk_dict.get("document_id", "")

                    # Try different path formats
                    possible_paths = [
                        f"data/extracted/{dataset_name}/{document_id}.xml",
                        f"./data/extracted/{dataset_name}/{document_id}.xml",
                        str(Path("data/extracted") / dataset_name / f"{document_id}.xml"),
                    ]

                    # Check if any of the possible paths match
                    if not any(path in file_paths for path in possible_paths) and not any(
                        document_id in fp for fp in file_paths
                    ):
                        continue

                # Validate that this is an enriched chunk
                if "embedding" not in chunk_dict:
                    raise ValueError(
                        f"Chunk {chunk_dict.get('chunk_id', 'unknown')} is missing "
                        f"embedding data. EnrichedChunkReader requires all chunks "
                        f"to have embeddings."
                    )

                try:
                    yield EnrichedChunk(**chunk_dict)
                except Exception as e:
                    # Re-raise with more context
                    raise ValueError(
                        f"Failed to parse enriched chunk {chunk_dict.get('chunk_id', 'unknown')}: {e}"
                    ) from e

    def read_chunks_for_document(self, document_id: str) -> list[dict]:
        """Read all chunks for a specific document.

        Args:
            document_id: Document ID to filter by

        Returns:
            List of chunk dictionaries for the specified document
        """
        chunks = []

        if not self.chunks_file.exists():
            return chunks

        with jsonlines.open(self.chunks_file) as reader:
            for chunk in reader:
                if chunk.get("document_id") == document_id:
                    chunks.append(chunk)

        return chunks

    def read_all_chunks(self) -> Iterator[dict]:
        """Stream all chunks from the file (memory efficient).

        Yields:
            Dictionary for each chunk in the file
        """
        if not self.chunks_file.exists():
            return

        with jsonlines.open(self.chunks_file) as reader:
            yield from reader

    def count_chunks(self) -> int:
        """Count total number of chunks in file.

        Returns:
            Total number of chunks
        """
        if not self.chunks_file.exists():
            return 0

        count = 0
        with jsonlines.open(self.chunks_file) as reader:
            for _ in reader:
                count += 1

        return count

    def get_document_ids(self) -> set[str]:
        """Get set of all document IDs in the file.

        Returns:
            Set of document IDs
        """
        document_ids = set()

        if not self.chunks_file.exists():
            return document_ids

        with jsonlines.open(self.chunks_file) as reader:
            for chunk in reader:
                doc_id = chunk.get("document_id")
                if doc_id:
                    document_ids.add(doc_id)

        return document_ids

    def read_chunks(
        self, file_paths: set[str] | None = None
    ) -> Iterator[ChunkMetadata | EnrichedChunk]:
        """Read chunks, optionally filtered by file paths.

        Args:
            file_paths: Optional set of file paths to filter by.
                       If provided, only chunks from these files are returned.

        Yields:
            ChunkMetadata or EnrichedChunk object for each matching chunk
        """
        if not self.chunks_file.exists():
            return

        with jsonlines.open(self.chunks_file) as reader:
            for chunk_dict in reader:
                # If filtering by file paths, check if this chunk matches
                if file_paths is not None:
                    # Reconstruct the likely file path from chunk data
                    dataset_name = chunk_dict.get("dataset_name", "")
                    document_id = chunk_dict.get("document_id", "")

                    # Try different path formats
                    possible_paths = [
                        f"data/extracted/{dataset_name}/{document_id}.xml",
                        f"./data/extracted/{dataset_name}/{document_id}.xml",
                        str(Path("data/extracted") / dataset_name / f"{document_id}.xml"),
                    ]

                    # Check if any of the possible paths match
                    if not any(path in file_paths for path in possible_paths) and not any(
                        document_id in fp for fp in file_paths
                    ):
                        continue

                # Convert dict to appropriate chunk type
                try:
                    # Check if this is an enriched chunk (has embedding)
                    if "embedding" in chunk_dict:
                        chunk = EnrichedChunk(**chunk_dict)
                    else:
                        chunk = ChunkMetadata(**chunk_dict)
                    yield chunk
                except Exception:
                    # Skip malformed chunks
                    continue
