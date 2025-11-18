"""Custom IO Manager for legal chunks with streaming support.

This IO Manager handles serialization and storage of LegalChunk objects
with memory-efficient streaming for large datasets.
"""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dagster import ConfigurableIOManager, InputContext, OutputContext

if TYPE_CHECKING:
    from lovdata_pipeline.parsers import LegalChunk


class ChunksIOManager(ConfigurableIOManager):
    """IO Manager for streaming legal chunks to/from pickle files.

    This IO Manager provides memory-efficient handling of large chunk datasets:
    - For outputs: Accepts generators/iterators and streams batches to disk
    - For inputs: Loads all chunks (could be extended for streaming if needed)

    Attributes:
        base_dir: Base directory for storing chunk files
    """

    base_dir: str = "data/io_manager"

    def _get_path(self, context: OutputContext | InputContext) -> Path:
        """Get file path for asset output.

        Args:
            context: Dagster context with asset key information

        Returns:
            Path to pickle file for this asset
        """
        base_path = Path(self.base_dir)
        base_path.mkdir(parents=True, exist_ok=True)

        # Use asset key to generate filename
        asset_key = context.asset_key.path
        filename = "_".join(asset_key) + ".pickle"

        return base_path / filename

    def handle_output(self, context: OutputContext, obj: Any) -> None:
        """Save chunks to pickle file.

        Supports both regular lists and generators for memory efficiency.

        Args:
            context: Dagster output context
            obj: Either a list of chunks or a generator yielding chunk batches
        """
        filepath = self._get_path(context)

        # Remove old file if exists
        if filepath.exists():
            filepath.unlink()

        # Check if obj is a generator/iterator or a regular list
        if hasattr(obj, "__iter__") and not isinstance(obj, (list, tuple)):
            # Generator/iterator - stream batches
            total_chunks = 0
            total_batches = 0

            with open(filepath, "wb") as f:
                for batch in obj:
                    if batch:  # Only write non-empty batches
                        pickle.dump(batch, f)
                        total_chunks += len(batch)
                        total_batches += 1

            context.log.info(
                f"Streamed {total_chunks} chunks in {total_batches} batches to {filepath}"
            )

            # Add metadata
            context.add_output_metadata(
                {
                    "total_chunks": total_chunks,
                    "total_batches": total_batches,
                    "filepath": str(filepath),
                }
            )

        else:
            # Regular list - write directly
            with open(filepath, "wb") as f:
                pickle.dump(obj, f)

            context.log.info(f"Wrote {len(obj)} items to {filepath}")

            context.add_output_metadata(
                {
                    "total_items": len(obj),
                    "filepath": str(filepath),
                }
            )

    def load_input(self, context: InputContext) -> list[LegalChunk]:
        """Load chunks from pickle file.

        Loads all chunks into memory. For very large datasets, this could
        be extended to support streaming.

        Args:
            context: Dagster input context

        Returns:
            List of all LegalChunk objects
        """
        filepath = self._get_path(context)

        if not filepath.exists():
            raise FileNotFoundError(f"Chunks file not found: {filepath}")

        all_chunks = []

        with open(filepath, "rb") as f:
            while True:
                try:
                    batch = pickle.load(f)
                    # Handle both batched and non-batched data
                    if isinstance(batch, list):
                        all_chunks.extend(batch)
                    else:
                        all_chunks.append(batch)
                except EOFError:
                    break

        context.log.info(f"Loaded {len(all_chunks)} chunks from {filepath}")

        return all_chunks
