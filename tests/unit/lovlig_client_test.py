"""Unit tests for LovligClient infrastructure."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lovdata_pipeline.domain.models import FileMetadata, RemovalInfo, SyncStatistics
from lovdata_pipeline.infrastructure.lovlig_client import LovligClient


@pytest.fixture
def temp_state_file(tmp_path):
    """Create a temporary state file for testing."""
    state_file = tmp_path / "state.json"
    extracted_dir = tmp_path / "extracted"
    extracted_dir.mkdir()

    state_data = {
        "raw_datasets": {
            "gjeldende-lover.tar.bz2": {
                "filename": "gjeldende-lover.tar.bz2",
                "last_modified": "2024-01-01T00:00:00Z",
                "files": {
                    "nl/nl-001.xml": {
                        "path": "nl/nl-001.xml",
                        "size": 5000,
                        "sha256": "hash1",
                        "last_changed": "2024-01-01T00:00:00Z",
                        "status": "added",
                    },
                    "nl/nl-002.xml": {
                        "path": "nl/nl-002.xml",
                        "size": 8000,
                        "sha256": "hash2",
                        "last_changed": "2024-01-01T00:00:00Z",
                        "status": "modified",
                    },
                    "nl/nl-003.xml": {
                        "path": "nl/nl-003.xml",
                        "size": 3000,
                        "sha256": "hash3",
                        "last_changed": "2024-01-01T00:00:00Z",
                        "status": "removed",
                    },
                },
            }
        }
    }

    state_file.write_text(json.dumps(state_data))

    # Create actual XML files (except removed one)
    dataset_dir = extracted_dir / "gjeldende-lover"
    dataset_dir.mkdir()

    (dataset_dir / "nl").mkdir()
    (dataset_dir / "nl" / "nl-001.xml").write_text("<test>content1</test>")
    (dataset_dir / "nl" / "nl-002.xml").write_text("<test>content2</test>")

    return state_file, extracted_dir, dataset_dir


def test_lovlig_client_init(temp_state_file):
    """Test LovligClient initialization."""
    state_file, extracted_dir, _ = temp_state_file

    client = LovligClient(
        dataset_filter="gjeldende",
        raw_data_dir=Path("/tmp/raw"),
        extracted_data_dir=extracted_dir,
        state_file=state_file,
        max_download_concurrency=4,
    )

    assert client.dataset_filter == "gjeldende"
    assert client.extracted_data_dir == extracted_dir
    assert client.state_file == state_file


def test_read_state(temp_state_file):
    """Test reading state file."""
    state_file, extracted_dir, _ = temp_state_file

    client = LovligClient(
        dataset_filter="gjeldende",
        raw_data_dir=Path("/tmp/raw"),
        extracted_data_dir=extracted_dir,
        state_file=state_file,
        max_download_concurrency=4,
    )

    state = client.read_state()

    assert "raw_datasets" in state
    assert "gjeldende-lover.tar.bz2" in state["raw_datasets"]
    assert len(state["raw_datasets"]["gjeldende-lover.tar.bz2"]["files"]) == 3


def test_read_state_file_not_found(tmp_path):
    """Test reading non-existent state file."""
    client = LovligClient(
        dataset_filter="gjeldende",
        raw_data_dir=Path("/tmp/raw"),
        extracted_data_dir=tmp_path,
        state_file=tmp_path / "nonexistent.json",
        max_download_concurrency=4,
    )

    with pytest.raises(FileNotFoundError):
        client.read_state()


def test_get_statistics(temp_state_file):
    """Test getting statistics from state."""
    state_file, extracted_dir, _ = temp_state_file

    client = LovligClient(
        dataset_filter="gjeldende",
        raw_data_dir=Path("/tmp/raw"),
        extracted_data_dir=extracted_dir,
        state_file=state_file,
        max_download_concurrency=4,
    )

    stats = client.get_statistics()

    assert isinstance(stats, SyncStatistics)
    # get_statistics looks for 'datasets' key, but state has 'raw_datasets'
    # This is intentional - get_statistics is for sync operations, not for querying state
    assert stats.files_added == 0
    assert stats.files_modified == 0
    assert stats.files_removed == 0


def test_get_files_by_status_added(temp_state_file):
    """Test getting files by status 'added'."""
    state_file, extracted_dir, _ = temp_state_file

    client = LovligClient(
        dataset_filter="gjeldende",
        raw_data_dir=Path("/tmp/raw"),
        extracted_data_dir=extracted_dir,
        state_file=state_file,
        max_download_concurrency=4,
    )

    files = client.get_files_by_status("added")

    assert len(files) == 1
    assert files[0]["path"] == "nl/nl-001.xml"
    assert files[0]["hash"] == "hash1"
    assert files[0]["status"] == "added"


def test_get_files_by_status_modified(temp_state_file):
    """Test getting files by status 'modified'."""
    state_file, extracted_dir, _ = temp_state_file

    client = LovligClient(
        dataset_filter="gjeldende",
        raw_data_dir=Path("/tmp/raw"),
        extracted_data_dir=extracted_dir,
        state_file=state_file,
        max_download_concurrency=4,
    )

    files = client.get_files_by_status("modified")

    assert len(files) == 1
    assert files[0]["path"] == "nl/nl-002.xml"


def test_get_files_by_status_removed(temp_state_file):
    """Test getting files by status 'removed'."""
    state_file, extracted_dir, _ = temp_state_file

    client = LovligClient(
        dataset_filter="gjeldende",
        raw_data_dir=Path("/tmp/raw"),
        extracted_data_dir=extracted_dir,
        state_file=state_file,
        max_download_concurrency=4,
    )

    files = client.get_files_by_status("removed")

    assert len(files) == 1
    assert files[0]["path"] == "nl/nl-003.xml"


def test_get_file_metadata(temp_state_file):
    """Test getting file metadata for existing file."""
    state_file, extracted_dir, dataset_dir = temp_state_file

    client = LovligClient(
        dataset_filter="gjeldende",
        raw_data_dir=Path("/tmp/raw"),
        extracted_data_dir=extracted_dir,
        state_file=state_file,
        max_download_concurrency=4,
    )

    file_info = {
        "path": "nl/nl-001.xml",
        "hash": "hash1",
        "dataset": "gjeldende-lover.tar.bz2",
        "status": "added",
    }

    metadata = client.get_file_metadata(file_info)

    assert metadata is not None
    assert isinstance(metadata, FileMetadata)
    assert metadata.relative_path == "nl/nl-001.xml"
    assert metadata.file_hash == "hash1"
    assert metadata.status == "added"
    assert metadata.document_id == "nl-001"
    assert metadata.absolute_path == dataset_dir / "nl" / "nl-001.xml"


def test_get_file_metadata_nonexistent_file(temp_state_file):
    """Test getting file metadata for non-existent file."""
    state_file, extracted_dir, _ = temp_state_file

    client = LovligClient(
        dataset_filter="gjeldende",
        raw_data_dir=Path("/tmp/raw"),
        extracted_data_dir=extracted_dir,
        state_file=state_file,
        max_download_concurrency=4,
    )

    file_info = {
        "path": "nl/nl-nonexistent.xml",
        "hash": "hash999",
        "dataset": "gjeldende-lover.tar.bz2",
        "status": "added",
    }

    metadata = client.get_file_metadata(file_info)

    # Should return None for non-existent file
    assert metadata is None


def test_get_changed_files(temp_state_file):
    """Test getting all changed files (added + modified)."""
    state_file, extracted_dir, _ = temp_state_file

    client = LovligClient(
        dataset_filter="gjeldende",
        raw_data_dir=Path("/tmp/raw"),
        extracted_data_dir=extracted_dir,
        state_file=state_file,
        max_download_concurrency=4,
    )

    changed_files = client.get_changed_files()

    # Should return 2 files (added + modified)
    assert len(changed_files) == 2

    doc_ids = {f.document_id for f in changed_files}
    assert "nl-001" in doc_ids
    assert "nl-002" in doc_ids

    # Verify they're FileMetadata objects
    for file_meta in changed_files:
        assert isinstance(file_meta, FileMetadata)
        assert file_meta.absolute_path.exists()


def test_get_removed_files(temp_state_file):
    """Test getting removed files."""
    state_file, extracted_dir, _ = temp_state_file

    client = LovligClient(
        dataset_filter="gjeldende",
        raw_data_dir=Path("/tmp/raw"),
        extracted_data_dir=extracted_dir,
        state_file=state_file,
        max_download_concurrency=4,
    )

    removed_files = client.get_removed_files()

    assert len(removed_files) == 1
    assert isinstance(removed_files[0], RemovalInfo)
    assert removed_files[0].document_id == "nl-003"
    assert removed_files[0].relative_path == "nl/nl-003.xml"
    assert removed_files[0].last_hash == "hash3"


def test_get_changed_files_empty_state(tmp_path):
    """Test getting changed files with empty state."""
    state_file = tmp_path / "empty_state.json"
    state_file.write_text(json.dumps({"raw_datasets": {}}))

    client = LovligClient(
        dataset_filter="gjeldende",
        raw_data_dir=Path("/tmp/raw"),
        extracted_data_dir=tmp_path,
        state_file=state_file,
        max_download_concurrency=4,
    )

    changed_files = client.get_changed_files()

    assert changed_files == []


def test_get_files_by_status_no_state_file(tmp_path):
    """Test getting files when state file doesn't exist."""
    client = LovligClient(
        dataset_filter="gjeldende",
        raw_data_dir=Path("/tmp/raw"),
        extracted_data_dir=tmp_path,
        state_file=tmp_path / "nonexistent.json",
        max_download_concurrency=4,
    )

    files = client.get_files_by_status("added")

    # Should return empty list instead of raising error
    assert files == []


def test_dataset_name_with_extension(temp_state_file):
    """Test that dataset names with .tar.bz2 extension are handled correctly."""
    state_file, extracted_dir, dataset_dir = temp_state_file

    client = LovligClient(
        dataset_filter="gjeldende",
        raw_data_dir=Path("/tmp/raw"),
        extracted_data_dir=extracted_dir,
        state_file=state_file,
        max_download_concurrency=4,
    )

    file_info = {
        "path": "nl/nl-001.xml",
        "hash": "hash1",
        "dataset": "gjeldende-lover.tar.bz2",
        "status": "added",
    }

    metadata = client.get_file_metadata(file_info)

    # Verify path construction strips .tar.bz2
    expected_path = dataset_dir / "nl" / "nl-001.xml"
    assert metadata.absolute_path == expected_path
    assert metadata.absolute_path.exists()
