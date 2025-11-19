"""Streaming JSONL writer for legal document chunks.

This module provides functionality to write chunks to JSONL format
one line at a time, ensuring memory-efficient output.
"""

import json
from pathlib import Path

from lovdata_pipeline.domain.models import ChunkMetadata


class ChunkWriter:
    """Write chunks to JSONL file in streaming fashion.

    Each chunk is written as a single line of JSON, allowing for
    efficient reading and processing by downstream systems.
    """

    def __init__(self, output_path: str | Path) -> None:
        """Initialize the chunk writer.

        Args:
            output_path: Path to the output JSONL file
        """
        self.output_path = Path(output_path)
        self.file_handle = None
        self.chunks_written = 0

    def open(self, mode: str = "a") -> None:
        """Open the file for writing.

        Args:
            mode: File open mode ('a' for append, 'w' for overwrite)
        """
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.file_handle = open(self.output_path, mode, encoding="utf-8")  # noqa: SIM115
        self.chunks_written = 0

    def write_chunk(self, chunk: ChunkMetadata) -> None:
        """Write a single chunk to the file.

        Args:
            chunk: ChunkMetadata to write

        Raises:
            RuntimeError: If file is not open
        """
        if self.file_handle is None:
            raise RuntimeError("File is not open. Call open() first.")

        # Convert to dict and write as JSON line
        chunk_dict = chunk.model_dump()
        json_line = json.dumps(chunk_dict, ensure_ascii=False)
        self.file_handle.write(json_line + "\n")
        self.chunks_written += 1

    def write_chunks(self, chunks: list[ChunkMetadata]) -> None:
        """Write multiple chunks to the file.

        Args:
            chunks: List of ChunkMetadata to write
        """
        for chunk in chunks:
            self.write_chunk(chunk)

    def close(self) -> None:
        """Close the file."""
        if self.file_handle is not None:
            self.file_handle.close()
            self.file_handle = None

    def clear(self) -> None:
        """Clear the output file (delete and recreate empty)."""
        if self.output_path.exists():
            self.output_path.unlink()

    def remove_chunks_for_document(self, document_id: str) -> int:
        """Remove all chunks for a specific document from the output file.

        This is used when a document is modified - we need to remove old chunks
        before writing new ones.

        Args:
            document_id: Document ID to remove chunks for

        Returns:
            Number of chunks removed
        """
        if not self.output_path.exists():
            return 0

        # Check if file is empty
        if self.output_path.stat().st_size == 0:
            return 0

        # Read all chunks except those matching the document_id
        temp_path = self.output_path.with_suffix(".tmp")
        removed_count = 0
        kept_count = 0

        with (
            open(self.output_path, encoding="utf-8") as infile,
            open(temp_path, "w", encoding="utf-8") as outfile,
        ):
            for line in infile:
                try:
                    chunk_data = json.loads(line)
                    if chunk_data.get("document_id") == document_id:
                        removed_count += 1
                    else:
                        outfile.write(line)
                        kept_count += 1
                except json.JSONDecodeError:
                    # Keep malformed lines
                    outfile.write(line)
                    kept_count += 1

        # Only replace if we kept some chunks or removed some
        # This prevents creating an empty file when processing new documents
        if kept_count > 0 or removed_count > 0:
            temp_path.replace(self.output_path)
        else:
            # Clean up temp file
            temp_path.unlink(missing_ok=True)

        return removed_count

    def get_file_size_mb(self) -> float:
        """Get the current size of the output file in MB.

        Returns:
            File size in megabytes, or 0 if file doesn't exist
        """
        if self.output_path.exists():
            return self.output_path.stat().st_size / (1024 * 1024)
        return 0.0

    def __enter__(self):
        """Context manager entry."""
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False
