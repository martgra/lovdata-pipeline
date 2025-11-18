"""Checkpoint service for resumable operations.

This service manages checkpoints for long-running operations,
enabling recovery from failures without re-processing completed work.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class Checkpoint:
    """Checkpoint data for resumable operations.

    Attributes:
        last_batch: Index of last successfully processed batch
        processed_ids: Set of IDs that have been processed
        timestamp: When this checkpoint was created
        total_processed: Total count of processed items
        metadata: Additional metadata for the checkpoint
    """

    last_batch: int
    processed_ids: set[str]
    timestamp: str
    total_processed: int
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict:
        """Convert checkpoint to serializable dictionary."""
        return {
            "last_batch": self.last_batch,
            "processed_ids": list(self.processed_ids),  # Convert set to list for JSON
            "timestamp": self.timestamp,
            "total_processed": self.total_processed,
            "metadata": self.metadata or {},
        }

    @classmethod
    def from_dict(cls, data: dict) -> Checkpoint:
        """Create checkpoint from dictionary."""
        return cls(
            last_batch=data.get("last_batch", 0),
            processed_ids=set(data.get("processed_ids", [])),  # Convert list back to set
            timestamp=data.get("timestamp", ""),
            total_processed=data.get("total_processed", 0),
            metadata=data.get("metadata"),
        )


class CheckpointService:
    """Service for managing operation checkpoints.

    This service provides checkpoint management for long-running operations,
    enabling recovery from failures. Checkpoints store only IDs and metadata,
    not the full data, to maintain memory efficiency.

    Example:
        >>> service = CheckpointService(checkpoint_dir=Path("data/checkpoints"))
        >>> checkpoint = service.load("run_123")
        >>> if checkpoint:
        >>>     start_batch = checkpoint.last_batch + 1
        >>>     processed_ids = checkpoint.processed_ids
    """

    def __init__(self, checkpoint_dir: Path | str):
        """Initialize checkpoint service.

        Args:
            checkpoint_dir: Directory to store checkpoint files
        """
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def _get_checkpoint_path(self, run_id: str, operation: str = "default") -> Path:
        """Get path to checkpoint file.

        Args:
            run_id: Unique identifier for the run (e.g., Dagster run_id)
            operation: Name of the operation (for multiple checkpoints per run)

        Returns:
            Path to checkpoint file
        """
        return self.checkpoint_dir / f"{operation}_{run_id}.json"

    def save(
        self,
        run_id: str,
        last_batch: int,
        processed_ids: set[str],
        total_processed: int,
        operation: str = "default",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Save checkpoint to disk.

        Args:
            run_id: Unique identifier for the run
            last_batch: Index of last successfully processed batch
            processed_ids: Set of IDs that have been processed
            total_processed: Total count of processed items
            operation: Name of the operation
            metadata: Additional metadata to store

        Returns:
            True if checkpoint saved successfully, False otherwise
        """
        checkpoint = Checkpoint(
            last_batch=last_batch,
            processed_ids=processed_ids,
            timestamp=datetime.now(UTC).isoformat(),
            total_processed=total_processed,
            metadata=metadata,
        )

        checkpoint_path = self._get_checkpoint_path(run_id, operation)

        try:
            with open(checkpoint_path, "w") as f:
                json.dump(checkpoint.to_dict(), f, indent=2)
            return True
        except Exception:
            return False

    def load(self, run_id: str, operation: str = "default") -> Checkpoint | None:
        """Load checkpoint from disk.

        Args:
            run_id: Unique identifier for the run
            operation: Name of the operation

        Returns:
            Checkpoint object if exists, None otherwise
        """
        checkpoint_path = self._get_checkpoint_path(run_id, operation)

        if not checkpoint_path.exists():
            return None

        try:
            with open(checkpoint_path) as f:
                data = json.load(f)
            return Checkpoint.from_dict(data)
        except Exception:
            return None

    def delete(self, run_id: str, operation: str = "default") -> bool:
        """Delete checkpoint file.

        Args:
            run_id: Unique identifier for the run
            operation: Name of the operation

        Returns:
            True if deleted successfully, False otherwise
        """
        checkpoint_path = self._get_checkpoint_path(run_id, operation)

        try:
            if checkpoint_path.exists():
                checkpoint_path.unlink()
            return True
        except Exception:
            return False

    def exists(self, run_id: str, operation: str = "default") -> bool:
        """Check if checkpoint exists.

        Args:
            run_id: Unique identifier for the run
            operation: Name of the operation

        Returns:
            True if checkpoint exists, False otherwise
        """
        checkpoint_path = self._get_checkpoint_path(run_id, operation)
        return checkpoint_path.exists()
