"""Tests for simplified lovlig wrapper."""

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from lovdata_pipeline.lovlig import Lovlig


@pytest.fixture
def temp_lovlig_setup(tmp_path):
    """Create temporary lovlig directory structure."""
    raw_dir = tmp_path / "raw"
    extracted_dir = tmp_path / "extracted"
    state_file = tmp_path / "state.json"

    raw_dir.mkdir()
    extracted_dir.mkdir()

    # Create sample state.json
    state_data = {
        "raw_datasets": {
            "gjeldende-lover.tar.bz2": {
                "files": {
                    "nl/nl-001.xml": {
                        "status": "added",
                        "sha256": "hash1",
                    },
                    "nl/nl-002.xml": {
                        "status": "modified",
                        "sha256": "hash2",
                    },
                    "nl/nl-003.xml": {
                        "status": "removed",
                        "sha256": "hash3",
                    },
                }
            }
        }
    }
    state_file.write_text(json.dumps(state_data))

    # Create sample XML files
    dataset_dir = extracted_dir / "gjeldende-lover" / "nl"
    dataset_dir.mkdir(parents=True)
    (dataset_dir / "nl-001.xml").write_text("<doc>Test 1</doc>")
    (dataset_dir / "nl-002.xml").write_text("<doc>Test 2</doc>")

    return {
        "raw_dir": raw_dir,
        "extracted_dir": extracted_dir,
        "state_file": state_file,
    }


def test_get_changed_files(temp_lovlig_setup):
    """Test getting changed files."""
    lovlig = Lovlig(
        dataset_filter="gjeldende",
        raw_dir=temp_lovlig_setup["raw_dir"],
        extracted_dir=temp_lovlig_setup["extracted_dir"],
        state_file=temp_lovlig_setup["state_file"],
    )

    changed = lovlig.get_changed_files()

    # Should return added and modified (not removed)
    assert len(changed) == 2

    doc_ids = {f.doc_id for f in changed}
    assert "nl-001" in doc_ids
    assert "nl-002" in doc_ids
    assert "nl-003" not in doc_ids

    # Check structure
    for file_info in changed:
        assert file_info.doc_id
        assert file_info.path
        assert file_info.hash
        assert file_info.dataset


def test_get_removed_files(temp_lovlig_setup):
    """Test getting removed files."""
    lovlig = Lovlig(
        dataset_filter="gjeldende",
        raw_dir=temp_lovlig_setup["raw_dir"],
        extracted_dir=temp_lovlig_setup["extracted_dir"],
        state_file=temp_lovlig_setup["state_file"],
    )

    removed = lovlig.get_removed_files()

    assert len(removed) == 1
    assert removed[0].doc_id == "nl-003"
    assert removed[0].dataset == "gjeldende-lover.tar.bz2"


def test_empty_state_file(tmp_path):
    """Test handling empty/missing state file."""
    lovlig = Lovlig(
        dataset_filter="gjeldende",
        raw_dir=tmp_path / "raw",
        extracted_dir=tmp_path / "extracted",
        state_file=tmp_path / "nonexistent.json",
    )

    changed = lovlig.get_changed_files()
    removed = lovlig.get_removed_files()

    assert not changed
    assert not removed


@patch("lovdata_pipeline.lovlig.sync_datasets")
def test_sync(mock_sync, tmp_path):
    """Test sync wrapper."""
    state_file = tmp_path / "state.json"

    # Setup state for stats
    state_file.write_text(
        json.dumps(
            {
                "raw_datasets": {
                    "test.tar.bz2": {
                        "files": {
                            "a.xml": {"status": "added"},
                            "b.xml": {"status": "modified"},
                            "c.xml": {"status": "removed"},
                        }
                    }
                }
            }
        )
    )

    lovlig = Lovlig(
        dataset_filter="gjeldende",
        raw_dir=tmp_path / "raw",
        extracted_dir=tmp_path / "extracted",
        state_file=state_file,
    )

    stats = lovlig.sync(force=False)

    # Check sync was called
    mock_sync.assert_called_once()
    call_kwargs = mock_sync.call_args.kwargs
    assert call_kwargs["force_download"] is False

    # Check stats
    assert stats.added == 1
    assert stats.modified == 1
    assert stats.removed == 1
