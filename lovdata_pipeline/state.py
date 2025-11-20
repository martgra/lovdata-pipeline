"""Simple state tracking for processed documents.

Just tracks which documents have been fully processed (with their hash and vector IDs).
"""

import json
from datetime import UTC, datetime
from pathlib import Path


class ProcessingState:
    """Minimal state tracker for pipeline.

    State structure:
    {
        "processed": {
            "doc-id": {"hash": "abc123", "at": "2025-11-19T..."},
        },
        "failed": {
            "doc-id": {"hash": "abc123", "error": "...", "at": "2025-11-19T..."}
        }
    }

    Note: We don't track vector IDs anymore. On failure, we delete all chunks
    by document_id metadata filter and reprocess from scratch.
    """

    def __init__(self, state_file: Path):
        """Initialize state tracker."""
        self.state_file = state_file
        self.state = self._load()

    def _load(self) -> dict:
        """Load state from disk."""
        if not self.state_file.exists():
            return {"processed": {}, "failed": {}}

        try:
            with open(self.state_file) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {"processed": {}, "failed": {}}

    def save(self):
        """Save state to disk atomically."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

        # Atomic write
        tmp = self.state_file.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(self.state, f, indent=2)
        tmp.replace(self.state_file)

    def is_processed(self, doc_id: str, file_hash: str) -> bool:
        """Check if document already processed with this hash."""
        if doc_id not in self.state["processed"]:
            return False
        return self.state["processed"][doc_id]["hash"] == file_hash

    def mark_processed(self, doc_id: str, file_hash: str):
        """Mark document as successfully processed."""
        self.state["processed"][doc_id] = {
            "hash": file_hash,
            "at": datetime.now(UTC).isoformat(),
        }
        self.state["failed"].pop(doc_id, None)

    def mark_failed(self, doc_id: str, file_hash: str, error: str):
        """Mark document as failed."""
        self.state["failed"][doc_id] = {
            "hash": file_hash,
            "error": error,
            "at": datetime.now(UTC).isoformat(),
        }

    def remove(self, doc_id: str):
        """Remove document from state."""
        self.state["processed"].pop(doc_id, None)
        self.state["failed"].pop(doc_id, None)

    def stats(self) -> dict:
        """Get summary statistics."""
        return {
            "processed": len(self.state["processed"]),
            "failed": len(self.state["failed"]),
        }
