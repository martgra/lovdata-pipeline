"""Tests for simplified state tracking."""

from pathlib import Path

import pytest

from lovdata_pipeline.state import ProcessingState


def test_create_new_state(tmp_path):
    """Test creating a new state file."""
    state_file = tmp_path / "state.json"
    state = ProcessingState(state_file)

    assert state.state == {"processed": {}, "failed": {}}
    assert not state_file.exists()  # Not saved yet


def test_mark_processed(tmp_path):
    """Test marking a document as processed."""
    state_file = tmp_path / "state.json"
    state = ProcessingState(state_file)

    state.mark_processed("doc-1", "hash-abc", ["vec1", "vec2", "vec3"])
    state.save()

    # Reload and verify
    state2 = ProcessingState(state_file)
    assert state2.is_processed("doc-1", "hash-abc")
    assert state2.get_vectors("doc-1") == ["vec1", "vec2", "vec3"]


def test_is_processed_checks_hash(tmp_path):
    """Test that is_processed checks the hash."""
    state = ProcessingState(tmp_path / "state.json")

    state.mark_processed("doc-1", "hash-abc", ["vec1"])

    # Same hash - should be processed
    assert state.is_processed("doc-1", "hash-abc")

    # Different hash - should NOT be processed
    assert not state.is_processed("doc-1", "hash-xyz")

    # Different doc - should NOT be processed
    assert not state.is_processed("doc-2", "hash-abc")


def test_mark_failed(tmp_path):
    """Test marking a document as failed."""
    state = ProcessingState(tmp_path / "state.json")

    state.mark_failed("doc-1", "hash-abc", "Parse error")
    state.save()

    # Verify failed entry
    assert "doc-1" in state.state["failed"]
    assert state.state["failed"]["doc-1"]["error"] == "Parse error"


def test_mark_processed_removes_failed(tmp_path):
    """Test that marking as processed removes from failed."""
    state = ProcessingState(tmp_path / "state.json")

    # First fail
    state.mark_failed("doc-1", "hash-abc", "Error")
    assert "doc-1" in state.state["failed"]

    # Then succeed
    state.mark_processed("doc-1", "hash-abc", ["vec1"])
    assert "doc-1" not in state.state["failed"]
    assert "doc-1" in state.state["processed"]


def test_remove_document(tmp_path):
    """Test removing a document from state."""
    state = ProcessingState(tmp_path / "state.json")

    state.mark_processed("doc-1", "hash-abc", ["vec1"])
    state.mark_failed("doc-2", "hash-xyz", "Error")

    state.remove("doc-1")
    state.remove("doc-2")

    assert "doc-1" not in state.state["processed"]
    assert "doc-2" not in state.state["failed"]


def test_stats(tmp_path):
    """Test getting statistics."""
    state = ProcessingState(tmp_path / "state.json")

    state.mark_processed("doc-1", "hash-1", ["v1", "v2"])
    state.mark_processed("doc-2", "hash-2", ["v3", "v4", "v5"])
    state.mark_failed("doc-3", "hash-3", "Error")

    stats = state.stats()
    assert stats["processed"] == 2
    assert stats["failed"] == 1
    assert stats["total_vectors"] == 5


def test_corrupted_state_file(tmp_path):
    """Test handling of corrupted state file."""
    state_file = tmp_path / "state.json"

    # Write invalid JSON
    state_file.write_text("not valid json {{{")

    # Should create new empty state
    state = ProcessingState(state_file)
    assert state.state == {"processed": {}, "failed": {}}
