"""Test that pipeline state is isolated from lovlig state updates.

This tests the critical scenario where lovlig's state.json is updated
between pipeline runs, ensuring we don't lose track of unprocessed files.
"""

from pathlib import Path
from unittest.mock import Mock

import pytest

from lovdata_pipeline.domain.models import FileInfo, PipelineConfig
from lovdata_pipeline.orchestration.pipeline_orchestrator import PipelineOrchestrator
from lovdata_pipeline.state import ProcessingState


def test_pipeline_state_isolated_from_lovlig_state_updates(tmp_path):
    """Test that pipeline uses its own state, not lovlig's state.

    Scenario:
    1. Initial sync: lovlig marks file1 as 'added', file2 as 'modified'
    2. Pipeline processes file1 successfully
    3. Another sync runs (before file2 is processed): lovlig marks everything 'unchanged'
    4. Pipeline should still see file2 as needing processing

    This prevents data loss when lovlig's state.json is overwritten between runs.
    """
    # Setup
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    pipeline_state_file = data_dir / "pipeline_state.json"

    # Create mock vector store
    mock_vector_store = Mock()
    mock_vector_store.count.return_value = 0

    # Create mock file processor
    mock_processor = Mock()

    # Create orchestrator
    orchestrator = PipelineOrchestrator(
        file_processor=mock_processor,
        vector_store=mock_vector_store,
    )

    # Create pipeline state
    state = ProcessingState(pipeline_state_file)

    # Simulate: file1 is processed, file2 is not
    state.mark_processed("doc1", "hash1_v1")
    state.save()

    # Create mock lovlig that returns both files as "changed"
    # (even though lovlig's state.json might say "unchanged" after a fresh sync)
    mock_lovlig = Mock()
    mock_lovlig.get_changed_files.return_value = [
        Mock(doc_id="doc1", path=Path("/fake/doc1.xml"), dataset="lov", hash="hash1_v1"),
        Mock(doc_id="doc2", path=Path("/fake/doc2.xml"), dataset="lov", hash="hash2_v1"),
    ]
    mock_lovlig.get_removed_files.return_value = []

    # Call _identify_files (the critical method)
    to_process, _ = orchestrator._identify_files(
        lovlig=mock_lovlig,
        state=state,
        force=False,
        progress_tracker=Mock(),
        limit=None,
    )

    # Assert: Only doc2 should be in the to_process list
    # doc1 should be skipped because it's in OUR pipeline_state.json
    assert len(to_process) == 1
    assert to_process[0].doc_id == "doc2"
    assert to_process[0].hash == "hash2_v1"


def test_hash_change_triggers_reprocessing(tmp_path):
    """Test that files with changed hashes are reprocessed.

    Even if a file is in our pipeline_state.json, if the hash changes
    (file was modified), we should reprocess it.
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    pipeline_state_file = data_dir / "pipeline_state.json"

    mock_vector_store = Mock()
    mock_vector_store.count.return_value = 0

    mock_processor = Mock()

    orchestrator = PipelineOrchestrator(
        file_processor=mock_processor,
        vector_store=mock_vector_store,
    )

    state = ProcessingState(pipeline_state_file)

    # File was processed with hash_v1
    state.mark_processed("doc1", "hash_v1")
    state.save()

    # Now lovlig reports the same file with hash_v2 (file was modified)
    mock_lovlig = Mock()
    mock_lovlig.get_changed_files.return_value = [
        Mock(doc_id="doc1", path=Path("/fake/doc1.xml"), dataset="lov", hash="hash_v2"),
    ]
    mock_lovlig.get_removed_files.return_value = []

    to_process, _ = orchestrator._identify_files(
        lovlig=mock_lovlig,
        state=state,
        force=False,
        progress_tracker=Mock(),
        limit=None,
    )

    # Assert: File should be reprocessed because hash changed
    assert len(to_process) == 1
    assert to_process[0].doc_id == "doc1"
    assert to_process[0].hash == "hash_v2"


def test_force_ignores_both_states(tmp_path):
    """Test that force=True reprocesses everything regardless of state."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    pipeline_state_file = data_dir / "pipeline_state.json"

    mock_vector_store = Mock()
    mock_vector_store.count.return_value = 0

    mock_processor = Mock()

    orchestrator = PipelineOrchestrator(
        file_processor=mock_processor,
        vector_store=mock_vector_store,
    )

    state = ProcessingState(pipeline_state_file)
    state.mark_processed("doc1", "hash1_v1")
    state.mark_processed("doc2", "hash2_v1")
    state.save()

    # Mock lovlig to return all files
    mock_lovlig = Mock()
    mock_lovlig.get_all_files.return_value = [
        Mock(doc_id="doc1", path=Path("/fake/doc1.xml"), dataset="lov", hash="hash1_v1"),
        Mock(doc_id="doc2", path=Path("/fake/doc2.xml"), dataset="lov", hash="hash2_v1"),
        Mock(doc_id="doc3", path=Path("/fake/doc3.xml"), dataset="lov", hash="hash3_v1"),
    ]
    mock_lovlig.get_removed_files.return_value = []

    to_process, _ = orchestrator._identify_files(
        lovlig=mock_lovlig,
        state=state,
        force=True,  # Force reprocessing
        progress_tracker=Mock(),
        limit=None,
    )

    # Assert: All files should be processed
    assert len(to_process) == 3
    doc_ids = [f.doc_id for f in to_process]
    assert "doc1" in doc_ids
    assert "doc2" in doc_ids
    assert "doc3" in doc_ids


def test_new_dataset_doesnt_lose_unprocessed_files(tmp_path):
    """Test the exact scenario: new dataset appears, old files not yet processed.

    Critical scenario you described:
    1. Initial sync: 100 files marked as 'added'
    2. Pipeline starts processing, completes 50 files
    3. NEW: Another dataset appears, lovlig syncs again
    4. lovlig's state.json gets overwritten, old 50 unprocessed files marked 'unchanged'
    5. Pipeline should STILL process those 50 files using OUR pipeline_state.json

    This is the data integrity issue you identified - we must use pipeline_state.json
    as the source of truth, not lovlig's state.json.
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    pipeline_state_file = data_dir / "pipeline_state.json"

    mock_vector_store = Mock()
    mock_vector_store.count.return_value = 0

    mock_processor = Mock()

    orchestrator = PipelineOrchestrator(
        file_processor=mock_processor,
        vector_store=mock_vector_store,
    )

    state = ProcessingState(pipeline_state_file)

    # Simulate: 50 files processed, 50 files NOT processed yet
    for i in range(1, 51):
        state.mark_processed(f"doc{i}", f"hash{i}_v1")
    state.save()

    # Mock lovlig AFTER a new sync that marked everything as 'unchanged'
    # but we still report them as "changed" from lovlig.get_changed_files()
    # because that method reads the current state, not historical changes
    mock_lovlig = Mock()

    # lovlig reports all 100 files (even though state.json might say "unchanged")
    all_files = [
        Mock(doc_id=f"doc{i}", path=Path(f"/fake/doc{i}.xml"), dataset="lov", hash=f"hash{i}_v1")
        for i in range(1, 101)
    ]
    mock_lovlig.get_changed_files.return_value = all_files
    mock_lovlig.get_removed_files.return_value = []

    to_process, _ = orchestrator._identify_files(
        lovlig=mock_lovlig,
        state=state,
        force=False,
        progress_tracker=Mock(),
        limit=None,
    )

    # Assert: Only the 50 unprocessed files should be in to_process
    assert len(to_process) == 50

    # Verify it's docs 51-100 (the unprocessed ones)
    doc_ids = {f.doc_id for f in to_process}
    for i in range(1, 51):
        assert f"doc{i}" not in doc_ids  # Already processed
    for i in range(51, 101):
        assert f"doc{i}" in doc_ids  # Not yet processed
