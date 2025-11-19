"""Reader for extracting chunks from JSONL files.

This module provides functionality to read chunks from the legal_chunks.jsonl
file by document ID, supporting memory-efficient streaming.
"""

import json
from collections.abc import Iterator
from pathlib import Path


class ChunkReader:
    """Read chunks from JSONL file by document ID.

    Provides methods to read chunks for specific documents or stream
    all chunks from the file.

    Args:
        chunks_file: Path to the JSONL file containing chunks
    """

    def __init__(self, chunks_file: Path):
        """Initialize the chunk reader."""
        self.chunks_file = chunks_file

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

        with open(self.chunks_file, encoding="utf-8") as f:
            for line in f:
                try:
                    chunk = json.loads(line)
                    if chunk.get("document_id") == document_id:
                        chunks.append(chunk)
                except json.JSONDecodeError:
                    # Skip malformed lines
                    continue

        return chunks

    def read_all_chunks(self) -> Iterator[dict]:
        """Stream all chunks from the file (memory efficient).

        Yields:
            Dictionary for each chunk in the file
        """
        if not self.chunks_file.exists():
            return

        with open(self.chunks_file, encoding="utf-8") as f:
            for line in f:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    # Skip malformed lines
                    continue

    def count_chunks(self) -> int:
        """Count total number of chunks in file.

        Returns:
            Total number of chunks
        """
        if not self.chunks_file.exists():
            return 0

        count = 0
        with open(self.chunks_file, encoding="utf-8") as f:
            for line in f:
                try:
                    json.loads(line)  # Validate JSON
                    count += 1
                except json.JSONDecodeError:
                    continue

        return count

    def get_document_ids(self) -> set[str]:
        """Get set of all document IDs in the file.

        Returns:
            Set of document IDs
        """
        document_ids = set()

        if not self.chunks_file.exists():
            return document_ids

        with open(self.chunks_file, encoding="utf-8") as f:
            for line in f:
                try:
                    chunk = json.loads(line)
                    doc_id = chunk.get("document_id")
                    if doc_id:
                        document_ids.add(doc_id)
                except json.JSONDecodeError:
                    continue

        return document_ids
