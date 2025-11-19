"""Unit tests for domain models."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from lovdata_pipeline.domain.models import ChunkMetadata, FileMetadata, RemovalInfo, SyncStatistics


def test_sync_statistics_total_changed():
    """Test that total_changed property works correctly."""
    stats = SyncStatistics(files_added=5, files_modified=3, files_removed=2, duration_seconds=10.5)

    assert stats.total_changed == 8
    assert stats.files_added == 5
    assert stats.files_modified == 3
    assert stats.files_removed == 2


def test_sync_statistics_validation():
    """Test that Pydantic validation works."""
    # Valid data
    stats = SyncStatistics(files_added=0, files_modified=0, files_removed=0)
    assert stats.files_added == 0

    # Negative values should be rejected
    with pytest.raises(ValidationError):
        SyncStatistics(files_added=-1, files_modified=0, files_removed=0)


def test_file_metadata_serialization():
    """Test FileMetadata serialization with Pydantic."""
    metadata = FileMetadata(
        relative_path="gjeldende-lover/LOV-2024-01-01.xml",
        absolute_path=Path("/data/extracted/gjeldende-lover/LOV-2024-01-01.xml"),
        file_hash="abc123",
        dataset_name="gjeldende-lover",
        status="added",
        file_size_bytes=1024,
        document_id="LOV-2024-01-01",
    )

    # Use model_dump_custom for dict with string path
    result = metadata.model_dump_custom()

    assert result["relative_path"] == "gjeldende-lover/LOV-2024-01-01.xml"
    assert result["document_id"] == "LOV-2024-01-01"
    assert result["status"] == "added"
    assert result["file_size_bytes"] == 1024
    assert isinstance(result["absolute_path"], str)


def test_removal_info_serialization():
    """Test RemovalInfo serialization with Pydantic."""
    info = RemovalInfo(
        document_id="LOV-2024-01-01",
        relative_path="gjeldende-lover/LOV-2024-01-01.xml",
        dataset_name="gjeldende-lover",
        last_hash="abc123",
    )

    # Use Pydantic's model_dump
    result = info.model_dump()

    assert result["document_id"] == "LOV-2024-01-01"
    assert result["relative_path"] == "gjeldende-lover/LOV-2024-01-01.xml"
    assert result["last_hash"] == "abc123"


def test_chunk_metadata_creation():
    """Test ChunkMetadata creation and validation."""
    chunk = ChunkMetadata(
        chunk_id="doc1_art1",
        document_id="doc1",
        content="Legal text content",
        token_count=50,
        section_heading="§ 1",
        absolute_address="NL/lov/2024/§1",
        split_reason="none",
    )

    assert chunk.chunk_id == "doc1_art1"
    assert chunk.document_id == "doc1"
    assert chunk.token_count == 50
    assert chunk.split_reason == "none"
    assert chunk.parent_chunk_id is None


def test_chunk_metadata_with_parent():
    """Test ChunkMetadata with parent chunk reference."""
    chunk = ChunkMetadata(
        chunk_id="doc1_art1_sub_001",
        document_id="doc1",
        content="Sub-chunk content",
        token_count=30,
        section_heading="§ 1",
        absolute_address="NL/lov/2024/§1",
        split_reason="paragraph",
        parent_chunk_id="doc1_art1",
    )

    assert chunk.parent_chunk_id == "doc1_art1"
    assert chunk.split_reason == "paragraph"


def test_chunk_metadata_serialization():
    """Test ChunkMetadata serialization to dict."""
    chunk = ChunkMetadata(
        chunk_id="test_chunk",
        document_id="test_doc",
        content="Content with Norwegian: æøå",
        token_count=100,
        section_heading="§ 2",
        absolute_address="LOV/2024/§2",
        split_reason="sentence",
        parent_chunk_id="parent_chunk",
    )

    result = chunk.model_dump()

    assert result["chunk_id"] == "test_chunk"
    assert result["document_id"] == "test_doc"
    assert "æøå" in result["content"]
    assert result["token_count"] == 100
    assert result["split_reason"] == "sentence"
    assert result["parent_chunk_id"] == "parent_chunk"


def test_chunk_metadata_validation():
    """Test ChunkMetadata validation."""
    # Valid chunk
    chunk = ChunkMetadata(
        chunk_id="valid",
        document_id="doc",
        content="content",
        token_count=10,
    )
    assert chunk.token_count == 10

    # Negative token count should be rejected
    with pytest.raises(ValidationError):
        ChunkMetadata(
            chunk_id="invalid",
            document_id="doc",
            content="content",
            token_count=-1,
        )
