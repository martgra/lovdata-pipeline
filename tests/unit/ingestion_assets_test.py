"""Unit tests for ingestion assets."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from dagster import build_asset_context

from lovdata_pipeline.assets.ingestion import (
    changed_file_paths,
    lovdata_sync,
    removed_file_metadata,
)
from lovdata_pipeline.domain.models import FileMetadata, RemovalInfo, SyncStatistics


def test_lovdata_sync_success():
    """Test lovdata_sync asset with successful sync."""
    context = build_asset_context()
    mock_lovlig = MagicMock()

    # Mock successful sync
    mock_lovlig.sync_datasets.return_value = SyncStatistics(
        files_added=10, files_modified=5, files_removed=2, duration_seconds=12.5
    )
    mock_lovlig.clean_removed_files_from_processed_state.return_value = 2

    result = lovdata_sync(context, mock_lovlig)

    # Verify lovlig was called
    mock_lovlig.sync_datasets.assert_called_once_with(force_download=False)
    mock_lovlig.clean_removed_files_from_processed_state.assert_called_once()

    # Verify result metadata
    assert result.metadata["files_added"].value == 10
    assert result.metadata["files_modified"].value == 5
    assert result.metadata["files_removed"].value == 2
    assert result.metadata["total_changed"].value == 15
    assert result.metadata["duration_seconds"].value == 12.5


def test_lovdata_sync_no_changes():
    """Test lovdata_sync when no files changed."""
    context = build_asset_context()
    mock_lovlig = MagicMock()

    mock_lovlig.sync_datasets.return_value = SyncStatistics(
        files_added=0, files_modified=0, files_removed=0, duration_seconds=2.1
    )
    mock_lovlig.clean_removed_files_from_processed_state.return_value = 0

    result = lovdata_sync(context, mock_lovlig)

    assert result.metadata["total_changed"].value == 0


def test_lovdata_sync_handles_error():
    """Test lovdata_sync handles sync errors."""
    context = build_asset_context()
    mock_lovlig = MagicMock()

    mock_lovlig.sync_datasets.side_effect = Exception("Network error")

    with pytest.raises(Exception, match="Network error"):
        lovdata_sync(context, mock_lovlig)


def test_changed_file_paths_with_files():
    """Test changed_file_paths returns correct paths."""
    context = build_asset_context()
    mock_lovlig = MagicMock()

    # Mock file metadata
    mock_files = [
        FileMetadata(
            relative_path="nl/nl-001.xml",
            absolute_path=Path("/data/extracted/gjeldende-lover/nl/nl-001.xml"),
            file_hash="hash1",
            dataset_name="gjeldende-lover.tar.bz2",
            status="added",
            file_size_bytes=5000,
            document_id="nl-001",
        ),
        FileMetadata(
            relative_path="nl/nl-002.xml",
            absolute_path=Path("/data/extracted/gjeldende-lover/nl/nl-002.xml"),
            file_hash="hash2",
            dataset_name="gjeldende-lover.tar.bz2",
            status="modified",
            file_size_bytes=8000,
            document_id="nl-002",
        ),
    ]

    mock_lovlig.get_unprocessed_files.return_value = mock_files

    result = changed_file_paths(context, mock_lovlig)

    # Verify result
    assert len(result) == 2
    assert str(mock_files[0].absolute_path) in result
    assert str(mock_files[1].absolute_path) in result

    # Verify lovlig was called
    mock_lovlig.get_unprocessed_files.assert_called_once()


def test_changed_file_paths_empty():
    """Test changed_file_paths when no files changed."""
    context = build_asset_context()
    mock_lovlig = MagicMock()

    mock_lovlig.get_unprocessed_files.return_value = []

    result = changed_file_paths(context, mock_lovlig)

    assert result == []


def test_changed_file_paths_metadata():
    """Test changed_file_paths generates correct metadata."""
    context = build_asset_context()
    mock_lovlig = MagicMock()

    mock_files = [
        FileMetadata(
            relative_path="nl/nl-001.xml",
            absolute_path=Path("/data/extracted/gjeldende-lover/nl/nl-001.xml"),
            file_hash="hash1",
            dataset_name="gjeldende-lover.tar.bz2",
            status="added",
            file_size_bytes=1024 * 1024,  # 1 MB
            document_id="nl-001",
        ),
        FileMetadata(
            relative_path="nl/nl-002.xml",
            absolute_path=Path("/data/extracted/gjeldende-lover/nl/nl-002.xml"),
            file_hash="hash2",
            dataset_name="gjeldende-lover.tar.bz2",
            status="modified",
            file_size_bytes=2 * 1024 * 1024,  # 2 MB
            document_id="nl-002",
        ),
    ]

    mock_lovlig.get_unprocessed_files.return_value = mock_files

    # Need to capture metadata through context
    with patch.object(context, "add_output_metadata") as mock_add_metadata:
        result = changed_file_paths(context, mock_lovlig)

        # Verify metadata was added
        mock_add_metadata.assert_called_once()
        metadata = mock_add_metadata.call_args[0][0]

        assert metadata["file_count"].value == 2
        assert metadata["added_count"].value == 1
        assert metadata["modified_count"].value == 1
        assert metadata["total_size_mb"].value == 3.0  # 3 MB total


def test_removed_file_metadata_with_removals():
    """Test removed_file_metadata returns correct data."""
    context = build_asset_context()
    mock_lovlig = MagicMock()

    mock_removals = [
        RemovalInfo(
            document_id="nl-old-001",
            relative_path="nl/nl-old-001.xml",
            dataset_name="gjeldende-lover.tar.bz2",
            last_hash="hash_old_1",
        ),
        RemovalInfo(
            document_id="nl-old-002",
            relative_path="nl/nl-old-002.xml",
            dataset_name="gjeldende-lover.tar.bz2",
            last_hash="hash_old_2",
        ),
    ]

    mock_lovlig.get_removed_files.return_value = mock_removals

    result = removed_file_metadata(context, mock_lovlig)

    # Verify result - should be list of dicts
    assert len(result) == 2
    assert isinstance(result[0], dict)
    assert result[0]["document_id"] == "nl-old-001"
    assert result[0]["relative_path"] == "nl/nl-old-001.xml"
    assert result[1]["document_id"] == "nl-old-002"

    # Verify lovlig was called
    mock_lovlig.get_removed_files.assert_called_once()


def test_removed_file_metadata_empty():
    """Test removed_file_metadata when no files removed."""
    context = build_asset_context()
    mock_lovlig = MagicMock()

    mock_lovlig.get_removed_files.return_value = []

    result = removed_file_metadata(context, mock_lovlig)

    assert result == []


def test_removed_file_metadata_metadata():
    """Test removed_file_metadata generates correct metadata."""
    context = build_asset_context()
    mock_lovlig = MagicMock()

    mock_removals = [
        RemovalInfo(
            document_id="nl-old-001",
            relative_path="nl/nl-old-001.xml",
            dataset_name="gjeldende-lover.tar.bz2",
            last_hash="hash1",
        ),
        RemovalInfo(
            document_id="nl-old-002",
            relative_path="nl/nl-old-002.xml",
            dataset_name="gjeldende-lover.tar.bz2",
            last_hash="hash2",
        ),
        RemovalInfo(
            document_id="nl-old-003",
            relative_path="nl/nl-old-003.xml",
            dataset_name="gjeldende-lover.tar.bz2",
            last_hash="hash3",
        ),
    ]

    mock_lovlig.get_removed_files.return_value = mock_removals

    with patch.object(context, "add_output_metadata") as mock_add_metadata:
        result = removed_file_metadata(context, mock_lovlig)

        # Verify metadata
        mock_add_metadata.assert_called_once()
        metadata = mock_add_metadata.call_args[0][0]

        assert metadata["removed_count"].value == 3
        assert "document_ids" in metadata


def test_changed_file_paths_large_dataset():
    """Test changed_file_paths handles large number of files."""
    context = build_asset_context()
    mock_lovlig = MagicMock()

    # Create 1000 mock files
    mock_files = [
        FileMetadata(
            relative_path=f"nl/nl-{i:04d}.xml",
            absolute_path=Path(f"/data/extracted/gjeldende-lover/nl/nl-{i:04d}.xml"),
            file_hash=f"hash{i}",
            dataset_name="gjeldende-lover.tar.bz2",
            status="added",
            file_size_bytes=5000,
            document_id=f"nl-{i:04d}",
        )
        for i in range(1000)
    ]

    mock_lovlig.get_unprocessed_files.return_value = mock_files

    result = changed_file_paths(context, mock_lovlig)

    # Should return all paths
    assert len(result) == 1000

    # Verify metadata shows correct count
    with patch.object(context, "add_output_metadata") as mock_add_metadata:
        changed_file_paths(context, mock_lovlig)

        metadata = mock_add_metadata.call_args[0][0]
        assert metadata["file_count"].value == 1000


def test_changed_file_paths_mixed_statuses():
    """Test changed_file_paths with mixed added/modified files."""
    context = build_asset_context()
    mock_lovlig = MagicMock()

    mock_files = [
        FileMetadata(
            relative_path="nl/nl-001.xml",
            absolute_path=Path("/data/extracted/gjeldende-lover/nl/nl-001.xml"),
            file_hash="hash1",
            dataset_name="gjeldende-lover.tar.bz2",
            status="added",
            file_size_bytes=5000,
            document_id="nl-001",
        ),
        FileMetadata(
            relative_path="nl/nl-002.xml",
            absolute_path=Path("/data/extracted/gjeldende-lover/nl/nl-002.xml"),
            file_hash="hash2",
            dataset_name="gjeldende-lover.tar.bz2",
            status="added",
            file_size_bytes=5000,
            document_id="nl-002",
        ),
        FileMetadata(
            relative_path="nl/nl-003.xml",
            absolute_path=Path("/data/extracted/gjeldende-lover/nl/nl-003.xml"),
            file_hash="hash3",
            dataset_name="gjeldende-lover.tar.bz2",
            status="modified",
            file_size_bytes=5000,
            document_id="nl-003",
        ),
    ]

    mock_lovlig.get_unprocessed_files.return_value = mock_files

    with patch.object(context, "add_output_metadata") as mock_add_metadata:
        result = changed_file_paths(context, mock_lovlig)

        assert len(result) == 3

        metadata = mock_add_metadata.call_args[0][0]
        assert metadata["added_count"].value == 2
        assert metadata["modified_count"].value == 1
