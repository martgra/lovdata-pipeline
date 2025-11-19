"""Tests for pipeline manifest tracking.

Tests verify:
- Document creation and version tracking
- Stage progression (not_started → in_progress → completed)
- Error handling with classification
- Index status tracking
- Serialization/deserialization
- Query operations
"""

import json
from pathlib import Path

import pytest

from lovdata_pipeline.infrastructure.pipeline_manifest import (
    ErrorClassification,
    IndexStatus,
    PipelineManifest,
    StageStatus,
)


@pytest.fixture
def temp_manifest(tmp_path):
    """Create a temporary manifest file."""
    manifest_file = tmp_path / "test_manifest.json"
    return PipelineManifest(manifest_file)


def test_create_empty_manifest(temp_manifest):
    """Test creating an empty manifest."""
    assert temp_manifest.documents == {}
    assert temp_manifest.version == "1.0.0"


def test_ensure_document(temp_manifest):
    """Test creating a document in the manifest."""
    doc = temp_manifest.ensure_document(
        document_id="doc-123",
        dataset_name="test-dataset",
        relative_path="path/to/doc.xml",
        file_hash="abc123",
        file_size_bytes=1000,
    )

    assert doc.document_id == "doc-123"
    assert doc.dataset_name == "test-dataset"
    assert doc.current_version.file_hash == "abc123"
    assert doc.current_version.index_status == IndexStatus.PENDING


def test_stage_progression(temp_manifest):
    """Test progressing through pipeline stages."""
    # Create document
    temp_manifest.ensure_document(
        document_id="doc-123",
        dataset_name="test-dataset",
        relative_path="path/to/doc.xml",
        file_hash="abc123",
        file_size_bytes=1000,
    )

    # Start chunking
    temp_manifest.start_stage("doc-123", "abc123", "chunking")
    doc = temp_manifest.get_document("doc-123")
    assert doc.current_version.stages["chunking"].status == StageStatus.IN_PROGRESS
    assert doc.current_version.current_stage == "chunking"

    # Complete chunking
    temp_manifest.complete_stage(
        document_id="doc-123",
        file_hash="abc123",
        stage="chunking",
        output={"chunk_count": 45},
        metadata={"splitter": "XMLAware"},
    )
    doc = temp_manifest.get_document("doc-123")
    assert doc.current_version.stages["chunking"].status == StageStatus.COMPLETED
    assert doc.current_version.stages["chunking"].output.chunk_count == 45


def test_stage_failure(temp_manifest):
    """Test recording stage failure with error classification."""
    # Create document
    temp_manifest.ensure_document(
        document_id="doc-123",
        dataset_name="test-dataset",
        relative_path="path/to/doc.xml",
        file_hash="abc123",
        file_size_bytes=1000,
    )

    # Start and fail embedding
    temp_manifest.start_stage("doc-123", "abc123", "embedding")
    temp_manifest.fail_stage(
        document_id="doc-123",
        file_hash="abc123",
        stage="embedding",
        error_type="OpenAIAPIError",
        error_message="Rate limit exceeded",
        classification=ErrorClassification.TRANSIENT,
        retry_after="2025-11-19T10:00:00Z",
    )

    doc = temp_manifest.get_document("doc-123")
    stage = doc.current_version.stages["embedding"]
    assert stage.status == StageStatus.FAILED
    assert stage.error.type == "OpenAIAPIError"
    assert stage.error.classification == ErrorClassification.TRANSIENT
    assert stage.error.retry_count == 1


def test_permanent_failure_sets_index_failed(temp_manifest):
    """Test that permanent failures mark document as failed."""
    temp_manifest.ensure_document(
        document_id="doc-123",
        dataset_name="test-dataset",
        relative_path="path/to/doc.xml",
        file_hash="abc123",
        file_size_bytes=1000,
    )

    temp_manifest.start_stage("doc-123", "abc123", "chunking")
    temp_manifest.fail_stage(
        document_id="doc-123",
        file_hash="abc123",
        stage="chunking",
        error_type="XMLParseError",
        error_message="Invalid XML",
        classification=ErrorClassification.PERMANENT,
    )

    doc = temp_manifest.get_document("doc-123")
    assert doc.current_version.index_status == IndexStatus.FAILED


def test_index_status_update(temp_manifest):
    """Test updating index status."""
    temp_manifest.ensure_document(
        document_id="doc-123",
        dataset_name="test-dataset",
        relative_path="path/to/doc.xml",
        file_hash="abc123",
        file_size_bytes=1000,
    )

    temp_manifest.set_index_status("doc-123", IndexStatus.INDEXED)

    doc = temp_manifest.get_document("doc-123")
    assert doc.current_version.index_status == IndexStatus.INDEXED


def test_version_tracking(temp_manifest):
    """Test that document version changes are tracked."""
    # Create initial version
    temp_manifest.ensure_document(
        document_id="doc-123",
        dataset_name="test-dataset",
        relative_path="path/to/doc.xml",
        file_hash="abc123",
        file_size_bytes=1000,
    )

    # Complete processing
    temp_manifest.start_stage("doc-123", "abc123", "chunking")
    temp_manifest.complete_stage("doc-123", "abc123", "chunking")

    # File changes - new version
    temp_manifest.ensure_document(
        document_id="doc-123",
        dataset_name="test-dataset",
        relative_path="path/to/doc.xml",
        file_hash="def456",  # New hash
        file_size_bytes=1200,
    )

    doc = temp_manifest.get_document("doc-123")
    assert doc.current_version.file_hash == "def456"
    assert len(doc.version_history) == 1
    assert doc.version_history[0].file_hash == "abc123"


def test_save_and_load(temp_manifest):
    """Test manifest persistence."""
    # Create and populate manifest
    temp_manifest.ensure_document(
        document_id="doc-123",
        dataset_name="test-dataset",
        relative_path="path/to/doc.xml",
        file_hash="abc123",
        file_size_bytes=1000,
    )
    temp_manifest.start_stage("doc-123", "abc123", "chunking")
    temp_manifest.complete_stage("doc-123", "abc123", "chunking", output={"chunk_count": 45})

    # Save
    temp_manifest.save()
    assert temp_manifest.manifest_file.exists()

    # Load
    loaded = PipelineManifest.load(temp_manifest.manifest_file)
    assert len(loaded.documents) == 1
    doc = loaded.get_document("doc-123")
    assert doc.current_version.file_hash == "abc123"
    assert doc.current_version.stages["chunking"].status == StageStatus.COMPLETED
    assert doc.current_version.stages["chunking"].output.chunk_count == 45


def test_query_by_stage_status(temp_manifest):
    """Test querying documents by stage status."""
    # Create multiple documents in different stages
    temp_manifest.ensure_document("doc-1", "dataset", "path1", "hash1", 1000)
    temp_manifest.ensure_document("doc-2", "dataset", "path2", "hash2", 1000)
    temp_manifest.ensure_document("doc-3", "dataset", "path3", "hash3", 1000)

    # doc-1: chunking completed
    temp_manifest.start_stage("doc-1", "hash1", "chunking")
    temp_manifest.complete_stage("doc-1", "hash1", "chunking")

    # doc-2: chunking in progress
    temp_manifest.start_stage("doc-2", "hash2", "chunking")

    # doc-3: not started (no stages)

    # Query
    in_progress = temp_manifest.get_documents_by_stage_status("chunking", StageStatus.IN_PROGRESS)
    completed = temp_manifest.get_documents_by_stage_status("chunking", StageStatus.COMPLETED)
    not_started = temp_manifest.get_documents_by_stage_status("chunking", StageStatus.NOT_STARTED)

    assert len(in_progress) == 1
    assert in_progress[0].document_id == "doc-2"

    assert len(completed) == 1
    assert completed[0].document_id == "doc-1"

    assert len(not_started) == 1
    assert not_started[0].document_id == "doc-3"


def test_query_by_index_status(temp_manifest):
    """Test querying documents by index status."""
    temp_manifest.ensure_document("doc-1", "dataset", "path1", "hash1", 1000)
    temp_manifest.ensure_document("doc-2", "dataset", "path2", "hash2", 1000)

    temp_manifest.set_index_status("doc-1", IndexStatus.INDEXED)
    # doc-2 stays at default PENDING

    indexed = temp_manifest.get_documents_by_index_status(IndexStatus.INDEXED)
    pending = temp_manifest.get_documents_by_index_status(IndexStatus.PENDING)

    assert len(indexed) == 1
    assert indexed[0].document_id == "doc-1"

    assert len(pending) == 1
    assert pending[0].document_id == "doc-2"


def test_compute_summary(temp_manifest):
    """Test summary statistics computation."""
    # Create documents in various states
    temp_manifest.ensure_document("doc-1", "dataset", "path1", "hash1", 1000)
    temp_manifest.start_stage("doc-1", "hash1", "chunking")
    temp_manifest.complete_stage("doc-1", "hash1", "chunking")
    temp_manifest.set_index_status("doc-1", IndexStatus.INDEXED)

    temp_manifest.ensure_document("doc-2", "dataset", "path2", "hash2", 1000)
    temp_manifest.start_stage("doc-2", "hash2", "chunking")

    temp_manifest.ensure_document("doc-3", "dataset", "path3", "hash3", 1000)

    # Save to trigger summary computation
    temp_manifest.save()

    # Load and check summary
    with open(temp_manifest.manifest_file) as f:
        data = json.load(f)

    summary = data["summary"]
    assert summary["total_documents"] == 3
    assert "chunking" in summary["by_stage"]
    assert summary["by_index_status"]["indexed"] == 1
    assert summary["by_index_status"]["pending"] == 2


def test_retry_count_increment(temp_manifest):
    """Test that retry count increments on repeated failures."""
    temp_manifest.ensure_document("doc-1", "dataset", "path1", "hash1", 1000)
    temp_manifest.start_stage("doc-1", "hash1", "embedding")

    # Fail once
    temp_manifest.fail_stage(
        "doc-1",
        "hash1",
        "embedding",
        "TimeoutError",
        "Connection timeout",
        ErrorClassification.TRANSIENT,
    )
    doc = temp_manifest.get_document("doc-1")
    assert doc.current_version.stages["embedding"].error.retry_count == 1

    # Fail again
    temp_manifest.fail_stage(
        "doc-1",
        "hash1",
        "embedding",
        "TimeoutError",
        "Connection timeout",
        ErrorClassification.TRANSIENT,
    )
    doc = temp_manifest.get_document("doc-1")
    assert doc.current_version.stages["embedding"].error.retry_count == 2


def test_max_retries_sets_index_failed(temp_manifest):
    """Test that exceeding max retries marks document as failed."""
    temp_manifest.ensure_document("doc-1", "dataset", "path1", "hash1", 1000)
    temp_manifest.start_stage("doc-1", "hash1", "embedding")

    # Fail 3 times (default max_retries)
    for _ in range(3):
        temp_manifest.fail_stage(
            "doc-1",
            "hash1",
            "embedding",
            "TimeoutError",
            "Connection timeout",
            ErrorClassification.TRANSIENT,
        )

    doc = temp_manifest.get_document("doc-1")
    assert doc.current_version.stages["embedding"].error.retry_count == 3
    assert doc.current_version.index_status == IndexStatus.FAILED
