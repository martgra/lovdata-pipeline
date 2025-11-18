"""File service for streaming file operations.

This service provides memory-efficient file I/O for large datasets,
using streaming and batch processing to avoid loading entire files into memory.
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator

if TYPE_CHECKING:
    from lovdata_pipeline.parsers import LegalChunk


class FileService:
    """Service for memory-efficient file operations.

    This service handles reading and writing large datasets in a streaming
    fashion to minimize memory usage.
    """

    @staticmethod
    def write_json(file_path: Path | str, data: dict) -> bool:
        """Write data to JSON file.

        Args:
            file_path: Path to write file
            data: Dictionary to serialize

        Returns:
            True if successful, False otherwise
        """
        file_path = Path(file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(file_path, "w") as f:
                json.dump(data, f, indent=2)
            return True
        except Exception:
            return False

    @staticmethod
    def read_json(file_path: Path | str) -> dict | None:
        """Read JSON file.

        Args:
            file_path: Path to JSON file

        Returns:
            Parsed dictionary or None if error
        """
        file_path = Path(file_path)

        if not file_path.exists():
            return None

        try:
            with open(file_path) as f:
                return json.load(f)
        except Exception:
            return None

    @staticmethod
    def write_chunks_streaming(
        file_path: Path | str,
        chunk_batches: Iterator[list[LegalChunk]],
    ) -> tuple[int, int]:
        """Write chunks to pickle file in streaming batches.

        This writes batches as they're generated, avoiding loading all
        chunks into memory at once. Each batch is pickled separately
        and can be read back in streaming fashion.

        Args:
            file_path: Path to pickle file
            chunk_batches: Iterator/generator of chunk batches

        Returns:
            Tuple of (total_chunks, total_batches) written
        """
        file_path = Path(file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Remove old file if exists
        if file_path.exists():
            file_path.unlink()

        total_chunks = 0
        total_batches = 0

        with open(file_path, "wb") as f:
            for batch in chunk_batches:
                if batch:  # Only write non-empty batches
                    pickle.dump(batch, f)
                    total_chunks += len(batch)
                    total_batches += 1

        return total_chunks, total_batches

    @staticmethod
    def read_chunks_streaming(file_path: Path | str) -> Iterator[list[LegalChunk]]:
        """Read chunks from pickle file in streaming batches.

        This yields batches one at a time, avoiding loading the entire
        file into memory. Memory usage is proportional to batch size,
        not total file size.

        Args:
            file_path: Path to pickle file

        Yields:
            Batches of LegalChunk objects

        Example:
            >>> for batch in FileService.read_chunks_streaming("chunks.pickle"):
            >>>     process_batch(batch)  # Only one batch in memory at a time
        """
        file_path = Path(file_path)

        if not file_path.exists():
            return

        with open(file_path, "rb") as f:
            while True:
                try:
                    batch = pickle.load(f)
                    yield batch
                except EOFError:
                    break

    @staticmethod
    def load_all_chunks(file_path: Path | str) -> list[LegalChunk]:
        """Load all chunks from pickle file into memory.

        WARNING: This loads the entire file into memory. Use only when
        you need all chunks at once. For memory efficiency, prefer
        read_chunks_streaming().

        Args:
            file_path: Path to pickle file

        Returns:
            List of all LegalChunk objects
        """
        all_chunks = []

        for batch in FileService.read_chunks_streaming(file_path):
            all_chunks.extend(batch)

        return all_chunks

    @staticmethod
    def count_chunks(file_path: Path | str) -> int:
        """Count total chunks in pickle file without loading into memory.

        Args:
            file_path: Path to pickle file

        Returns:
            Total number of chunks
        """
        total = 0

        for batch in FileService.read_chunks_streaming(file_path):
            total += len(batch)

        return total

    @staticmethod
    def cleanup_temp_files(*file_paths: Path | str) -> list[str]:
        """Clean up temporary files.

        Args:
            *file_paths: Variable number of file paths to delete

        Returns:
            List of successfully deleted file paths
        """
        deleted = []

        for file_path in file_paths:
            try:
                file_path = Path(file_path)
                if file_path.exists():
                    file_path.unlink()
                    deleted.append(str(file_path))
            except Exception:
                continue

        return deleted

    @staticmethod
    def write_pickle_batches(
        file_path: Path | str,
        batches: list[list[Any]],
    ) -> bool:
        """Write multiple batches to pickle file.

        Args:
            file_path: Path to pickle file
            batches: List of batches to write

        Returns:
            True if successful, False otherwise
        """
        file_path = Path(file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Remove old file if exists
        if file_path.exists():
            file_path.unlink()

        try:
            with open(file_path, "wb") as f:
                for batch in batches:
                    if batch:
                        pickle.dump(batch, f)
            return True
        except Exception:
            return False
