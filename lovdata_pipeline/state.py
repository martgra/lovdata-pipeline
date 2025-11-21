"""Simple state tracking for processed documents.

This is our pipeline_state.json - the source of truth for what WE have processed.
This is separate from lovlig's state.json which tracks raw dataset sync state.

Two-state system:
1. lovlig's state.json: Tracks downloaded/extracted files and their hashes
2. pipeline_state.json (this): Tracks which files WE have fully processed

Why separate?
- If lovlig syncs again before processing completes, state.json gets overwritten
- pipeline_state.json preserves our processing history
- We always check pipeline_state.json to determine what needs processing
"""

import json
from datetime import UTC, datetime
from pathlib import Path

from lovdata_pipeline.domain.models import (
    FailedDocumentInfo,
    ProcessedDocumentInfo,
    ProcessingStateData,
)


class ProcessingState:
    """Minimal state tracker for pipeline.

    Tracks documents we've successfully processed with their hash.
    This is the authoritative source for "what has been processed",
    NOT lovlig's state.json.

    Note: We don't track vector IDs anymore. On failure, we delete all chunks
    by document_id metadata filter and reprocess from scratch.
    """

    def __init__(self, state_file: Path):
        """Initialize state tracker."""
        self.state_file = state_file
        self.state = self._load()

    def _load(self) -> ProcessingStateData:
        """Load state from disk."""
        if not self.state_file.exists():
            return ProcessingStateData()

        try:
            with open(self.state_file) as f:
                data = json.load(f)
                # Convert dict format to Pydantic models
                return ProcessingStateData(
                    processed={
                        k: ProcessedDocumentInfo(**v) for k, v in data.get("processed", {}).items()
                    },
                    failed={k: FailedDocumentInfo(**v) for k, v in data.get("failed", {}).items()},
                )
        except (json.JSONDecodeError, OSError):
            return ProcessingStateData()

    def save(self):
        """Save state to disk atomically."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

        # Convert Pydantic models to dict for JSON serialization
        data = {
            "processed": {k: v.model_dump() for k, v in self.state.processed.items()},
            "failed": {k: v.model_dump() for k, v in self.state.failed.items()},
        }

        # Atomic write
        tmp = self.state_file.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        tmp.replace(self.state_file)

    def is_processed(self, doc_id: str, file_hash: str) -> bool:
        """Check if document already processed with this hash."""
        if doc_id not in self.state.processed:
            return False
        return self.state.processed[doc_id].hash == file_hash

    def mark_processed(self, doc_id: str, file_hash: str):
        """Mark document as successfully processed."""
        self.state.processed[doc_id] = ProcessedDocumentInfo(
            hash=file_hash,
            at=datetime.now(UTC).isoformat(),
        )
        self.state.failed.pop(doc_id, None)

    def mark_failed(self, doc_id: str, file_hash: str, error: str):
        """Mark document as failed."""
        self.state.failed[doc_id] = FailedDocumentInfo(
            hash=file_hash,
            error=error,
            at=datetime.now(UTC).isoformat(),
        )

    def remove(self, doc_id: str):
        """Remove document from state."""
        self.state.processed.pop(doc_id, None)
        self.state.failed.pop(doc_id, None)

    def stats(self) -> dict:
        """Get summary statistics."""
        return {
            "processed": len(self.state.processed),
            "failed": len(self.state.failed),
        }
