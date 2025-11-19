"""Writer for enriched chunks with embeddings.

This module provides functionality to write enriched chunks (with embeddings)
to JSONL format, similar to ChunkWriter but for enriched data.
"""

from pathlib import Path

import jsonlines


class EnrichedChunkWriter:
    """Write enriched chunks to JSONL file in streaming fashion.

    Each enriched chunk is written as a single line of JSON, allowing for
    efficient reading and processing by downstream systems.

    Similar to ChunkWriter but handles enriched chunks with embeddings.

    Args:
        output_path: Path to the output JSONL file
    """

    def __init__(self, output_path: str | Path) -> None:
        """Initialize the enriched chunk writer."""
        self.output_path = Path(output_path)
        self.file_handle = None
        self.chunks_written = 0

    def open(self, mode: str = "a") -> None:
        """Open the file for writing.

        Args:
            mode: File open mode ('a' for append, 'w' for overwrite)
        """
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.file_handle = jsonlines.open(self.output_path, mode=mode)
        self.chunks_written = 0

    def write_chunk(self, enriched_chunk: dict) -> None:
        """Write a single enriched chunk to the file.

        Args:
            enriched_chunk: Enriched chunk dictionary (includes embedding)

        Raises:
            RuntimeError: If file is not open
        """
        if self.file_handle is None:
            raise RuntimeError("File is not open. Call open() first.")

        self.file_handle.write(enriched_chunk)
        self.chunks_written += 1

    def write_chunks(self, enriched_chunks: list[dict]) -> None:
        """Write multiple enriched chunks to the file.

        Args:
            enriched_chunks: List of enriched chunk dictionaries
        """
        for chunk in enriched_chunks:
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

        This is used when a document is modified or deleted - we need to remove
        old embeddings before writing new ones.

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
            jsonlines.open(self.output_path) as reader,
            jsonlines.open(temp_path, mode="w") as writer,
        ):
            for chunk_data in reader:
                if chunk_data.get("document_id") == document_id:
                    removed_count += 1
                else:
                    writer.write(chunk_data)
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

    def __exit__(self, _exc_type, _exc_val, _exc_tb):
        """Context manager exit."""
        self.close()
        return False
