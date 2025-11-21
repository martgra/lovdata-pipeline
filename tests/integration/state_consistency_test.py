"""Integration tests for state consistency across pipeline operations.

Tests edge cases and consistency requirements:
- State persistence after crashes/failures
- State-vector store synchronization
- Concurrent-like scenarios (rapid saves)
- Recovery from inconsistent states
"""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from lovdata_pipeline.domain.models import (
    FileInfo,
    FileProcessingResult,
    PipelineConfig,
)
from lovdata_pipeline.domain.services.file_processing_service import FileProcessingService
from lovdata_pipeline.domain.vector_store import VectorStoreRepository
from lovdata_pipeline.infrastructure.jsonl_vector_store import JsonlVectorStoreRepository
from lovdata_pipeline.orchestration.pipeline_orchestrator import PipelineOrchestrator
from lovdata_pipeline.state import ProcessingState


# Override mock_file_processor to store vectors (uses vector_store from conftest)
@pytest.fixture
def mock_file_processor(vector_store):
    """Mock file processor that actually stores mock vectors."""
    processor = Mock(spec=FileProcessingService)

    def process_with_vectors(file_info, progress_callback=None, warning_callback=None):
        """Process file and store mock vectors in the real vector store."""
        from lovdata_pipeline.domain.models import EnrichedChunk
        from datetime import datetime, UTC
        import numpy as np

        # Create mock enriched chunks
        chunks = []
        for i in range(3):  # Create 3 chunks per document
            chunk = EnrichedChunk(
                chunk_id=f"{file_info.doc_id}_chunk_{i}",
                document_id=file_info.doc_id,
                dataset_name=file_info.dataset,
                content=f"Mock content {i} for {file_info.doc_id}",
                token_count=50,
                section_heading="Test Section",
                absolute_address="",
                split_reason="none",
                parent_chunk_id=None,
                source_hash=file_info.hash,
                embedding=np.random.rand(1536).tolist(),  # Mock embedding
                embedding_model="text-embedding-3-large",
                embedded_at=datetime.now(UTC).isoformat(),
            )
            chunks.append(chunk)

        # Actually store in vector store
        vector_store.upsert_chunks(chunks)

        return FileProcessingResult(
            success=True,
            chunk_count=len(chunks),
            error_message=None,
        )

    processor.process_file.side_effect = process_with_vectors
    return processor


@pytest.fixture
def orchestrator(tmp_path, mock_file_processor, vector_store):
    """Orchestrator with real state and vector store."""
    return PipelineOrchestrator(
        file_processor=mock_file_processor,
        vector_store=vector_store,
    )


def test_state_survives_partial_processing_failure(tmp_path, orchestrator, mock_file_processor):
    """Test that state is preserved when processing fails mid-batch.

    Scenario: Process 5 files, fail on 3rd. State should have first 2 marked.
    """
    state_file = tmp_path / "pipeline_state.json"
    config = PipelineConfig(
        data_dir=tmp_path,
        dataset_filter="test",
        force=False,
        limit=None,
    )

    # Create test files
    extracted_dir = tmp_path / "extracted" / "test-dataset"
    extracted_dir.mkdir(parents=True)

    for i in range(1, 6):
        (extracted_dir / f"doc{i}.xml").write_text(f"<doc>Content {i}</doc>")

    # Configure processor to succeed first 2, fail on 3rd
    results = [
        FileProcessingResult(success=True, chunk_count=2, error_message=None),
        FileProcessingResult(success=True, chunk_count=2, error_message=None),
        FileProcessingResult(success=False, chunk_count=0, error_message="Parse error"),
        FileProcessingResult(success=True, chunk_count=2, error_message=None),
        FileProcessingResult(success=True, chunk_count=2, error_message=None),
    ]
    mock_file_processor.process_file.side_effect = results

    # Create mock lovlig
    from unittest.mock import patch, Mock
    from lovdata_pipeline.domain.models import LovligFileInfo, LovligSyncStats

    with patch("lovdata_pipeline.orchestration.pipeline_orchestrator.Lovlig") as mock_lovlig_class:
        mock_lovlig = Mock()
        mock_lovlig.state_file = tmp_path / "state.json"
        mock_lovlig.state_file.touch()

        mock_lovlig.get_changed_files.return_value = [
            LovligFileInfo(
                doc_id=f"doc{i}",
                path=extracted_dir / f"doc{i}.xml",
                dataset="test-dataset",
                hash=f"hash{i}",
            )
            for i in range(1, 6)
        ]
        mock_lovlig.get_removed_files.return_value = []
        mock_lovlig.get_all_files.return_value = []
        mock_lovlig.sync.return_value = LovligSyncStats(added=5, modified=0, removed=0)

        mock_lovlig_class.return_value = mock_lovlig

        # Run pipeline
        result = orchestrator.run(config)

        # Verify counts
        assert result.processed == 4  # 4 succeeded
        assert result.failed == 1  # 1 failed

        # Verify state consistency
        state = ProcessingState(state_file)
        assert len(state.state.processed) == 4
        assert len(state.state.failed) == 1

        # Verify successful docs are marked
        assert state.is_processed("doc1", "hash1")
        assert state.is_processed("doc2", "hash2")
        assert state.is_processed("doc4", "hash4")
        assert state.is_processed("doc5", "hash5")

        # Verify failed doc is marked
        assert "doc3" in state.state.failed
        assert state.state.failed["doc3"].error == "Parse error"


def test_state_and_vectors_stay_synchronized(tmp_path, orchestrator, mock_file_processor, vector_store):
    """Test that state tracking stays in sync with vector store.

    Critical: If doc is in processed state, its vectors must exist.
    """
    state_file = tmp_path / "pipeline_state.json"
    config = PipelineConfig(
        data_dir=tmp_path,
        dataset_filter="test",
        force=False,
        limit=None,
    )

    extracted_dir = tmp_path / "extracted" / "test-dataset"
    extracted_dir.mkdir(parents=True)

    (extracted_dir / "doc1.xml").write_text("<doc>Content 1</doc>")
    (extracted_dir / "doc2.xml").write_text("<doc>Content 2</doc>")

    from unittest.mock import patch, Mock
    from lovdata_pipeline.domain.models import LovligFileInfo, LovligSyncStats

    with patch("lovdata_pipeline.orchestration.pipeline_orchestrator.Lovlig") as mock_lovlig_class:
        mock_lovlig = Mock()
        mock_lovlig.state_file = tmp_path / "state.json"
        mock_lovlig.state_file.touch()

        mock_lovlig.get_changed_files.return_value = [
            LovligFileInfo(doc_id="doc1", path=extracted_dir / "doc1.xml", dataset="test-dataset", hash="hash1"),
            LovligFileInfo(doc_id="doc2", path=extracted_dir / "doc2.xml", dataset="test-dataset", hash="hash2"),
        ]
        mock_lovlig.get_removed_files.return_value = []
        mock_lovlig.get_all_files.return_value = []
        mock_lovlig.sync.return_value = LovligSyncStats(added=2, modified=0, removed=0)

        mock_lovlig_class.return_value = mock_lovlig

        # Run pipeline
        orchestrator.run(config)

        # Verify state
        state = ProcessingState(state_file)
        assert state.is_processed("doc1", "hash1")
        assert state.is_processed("doc2", "hash2")

        # Verify vectors exist for all processed docs
        doc1_chunks = vector_store.get_chunks_by_document_id("doc1")
        doc2_chunks = vector_store.get_chunks_by_document_id("doc2")

        assert len(doc1_chunks) > 0, "Processed doc must have vectors"
        assert len(doc2_chunks) > 0, "Processed doc must have vectors"

        # Verify metadata consistency
        for chunk in doc1_chunks:
            assert chunk.metadata["document_id"] == "doc1"
        for chunk in doc2_chunks:
            assert chunk.metadata["document_id"] == "doc2"


def test_state_handles_hash_change_correctly(tmp_path, orchestrator, mock_file_processor):
    """Test that hash changes trigger reprocessing and state update.

    Scenario:
    1. Process doc1 with hash_v1
    2. Content changes (hash_v2)
    3. Should reprocess and update hash in state
    """
    state_file = tmp_path / "pipeline_state.json"
    config = PipelineConfig(
        data_dir=tmp_path,
        dataset_filter="test",
        force=False,
        limit=None,
    )

    extracted_dir = tmp_path / "extracted" / "test-dataset"
    extracted_dir.mkdir(parents=True)
    (extracted_dir / "doc1.xml").write_text("<doc>Original content</doc>")

    from unittest.mock import patch, Mock
    from lovdata_pipeline.domain.models import LovligFileInfo, LovligSyncStats

    with patch("lovdata_pipeline.orchestration.pipeline_orchestrator.Lovlig") as mock_lovlig_class:
        # First run: Process with hash_v1
        mock_lovlig1 = Mock()
        mock_lovlig1.state_file = tmp_path / "state.json"
        mock_lovlig1.state_file.touch()

        mock_lovlig1.get_changed_files.return_value = [
            LovligFileInfo(doc_id="doc1", path=extracted_dir / "doc1.xml", dataset="test", hash="hash_v1"),
        ]
        mock_lovlig1.get_removed_files.return_value = []
        mock_lovlig1.get_all_files.return_value = []
        mock_lovlig1.sync.return_value = LovligSyncStats(added=1, modified=0, removed=0)

        mock_lovlig_class.return_value = mock_lovlig1

        result1 = orchestrator.run(config)
        assert result1.processed == 1

        # Verify state after first run
        state1 = ProcessingState(state_file)
        assert state1.is_processed("doc1", "hash_v1")
        assert not state1.is_processed("doc1", "hash_v2")  # Different hash

        # Second run: Hash changed to hash_v2
        mock_lovlig2 = Mock()
        mock_lovlig2.state_file = tmp_path / "state.json"
        mock_lovlig2.state_file.touch()

        mock_lovlig2.get_changed_files.return_value = [
            LovligFileInfo(doc_id="doc1", path=extracted_dir / "doc1.xml", dataset="test", hash="hash_v2"),
        ]
        mock_lovlig2.get_removed_files.return_value = []
        mock_lovlig2.get_all_files.return_value = []
        mock_lovlig2.sync.return_value = LovligSyncStats(added=0, modified=1, removed=0)

        mock_lovlig_class.return_value = mock_lovlig2

        result2 = orchestrator.run(config)
        assert result2.processed == 1  # Should reprocess

        # Verify state updated to new hash
        state2 = ProcessingState(state_file)
        assert not state2.is_processed("doc1", "hash_v1")  # Old hash gone
        assert state2.is_processed("doc1", "hash_v2")  # New hash present


def test_state_recovery_from_failed_to_successful(tmp_path, orchestrator, mock_file_processor):
    """Test that failed documents can be retried and moved to processed state.

    Scenario:
    1. Doc fails processing (goes to failed state)
    2. Fix issue and retry
    3. Doc moves from failed to processed state
    """
    state_file = tmp_path / "pipeline_state.json"
    config = PipelineConfig(
        data_dir=tmp_path,
        dataset_filter="test",
        force=False,
        limit=None,
    )

    extracted_dir = tmp_path / "extracted" / "test-dataset"
    extracted_dir.mkdir(parents=True)
    (extracted_dir / "doc1.xml").write_text("<doc>Content</doc>")

    from unittest.mock import patch, Mock
    from lovdata_pipeline.domain.models import LovligFileInfo, LovligSyncStats

    with patch("lovdata_pipeline.orchestration.pipeline_orchestrator.Lovlig") as mock_lovlig_class:
        # First run: Fails
        mock_file_processor.process_file.side_effect = None  # Clear side effect
        mock_file_processor.process_file.return_value = FileProcessingResult(
            success=False,
            chunk_count=0,
            error_message="Temporary network error",
        )

        mock_lovlig1 = Mock()
        mock_lovlig1.state_file = tmp_path / "state.json"
        mock_lovlig1.state_file.touch()

        mock_lovlig1.get_changed_files.return_value = [
            LovligFileInfo(doc_id="doc1", path=extracted_dir / "doc1.xml", dataset="test", hash="hash1"),
        ]
        mock_lovlig1.get_removed_files.return_value = []
        mock_lovlig1.get_all_files.return_value = []
        mock_lovlig1.sync.return_value = LovligSyncStats(added=1, modified=0, removed=0)

        mock_lovlig_class.return_value = mock_lovlig1

        result1 = orchestrator.run(config)
        assert result1.failed == 1

        # Verify failed state
        state1 = ProcessingState(state_file)
        assert "doc1" in state1.state.failed
        assert "doc1" not in state1.state.processed
        assert state1.state.failed["doc1"].error == "Temporary network error"

        # Second run: Succeeds (network issue resolved)
        # Restore the side effect that stores vectors
        def process_with_vectors(file_info, progress_callback=None, warning_callback=None):
            from lovdata_pipeline.domain.models import EnrichedChunk
            from datetime import datetime, UTC
            import numpy as np

            chunks = []
            for i in range(3):
                chunk = EnrichedChunk(
                    chunk_id=f"{file_info.doc_id}_chunk_{i}",
                    document_id=file_info.doc_id,
                    dataset_name=file_info.dataset,
                    content=f"Mock content {i} for {file_info.doc_id}",
                    token_count=50,
                    section_heading="Test Section",
                    absolute_address="",
                    split_reason="none",
                    parent_chunk_id=None,
                    source_hash=file_info.hash,
                    embedding=np.random.rand(1536).tolist(),
                    embedding_model="text-embedding-3-large",
                    embedded_at=datetime.now(UTC).isoformat(),
                )
                chunks.append(chunk)

            # Get vector store from orchestrator
            orchestrator._vector_store.upsert_chunks(chunks)

            return FileProcessingResult(
                success=True,
                chunk_count=len(chunks),
                error_message=None,
            )

        mock_file_processor.process_file.side_effect = process_with_vectors

        # Mock lovlig still reports it as changed (for retry)
        mock_lovlig2 = Mock()
        mock_lovlig2.state_file = tmp_path / "state.json"
        mock_lovlig2.state_file.touch()

        mock_lovlig2.get_changed_files.return_value = [
            LovligFileInfo(doc_id="doc1", path=extracted_dir / "doc1.xml", dataset="test", hash="hash1"),
        ]
        mock_lovlig2.get_removed_files.return_value = []
        mock_lovlig2.get_all_files.return_value = []
        mock_lovlig2.sync.return_value = LovligSyncStats(added=0, modified=0, removed=0)

        mock_lovlig_class.return_value = mock_lovlig2

        result2 = orchestrator.run(config)
        assert result2.processed == 1

        # Verify recovery: moved from failed to processed
        state2 = ProcessingState(state_file)
        assert "doc1" not in state2.state.failed  # No longer failed
        assert "doc1" in state2.state.processed  # Now processed
        assert state2.is_processed("doc1", "hash1")


def test_state_removal_consistency(tmp_path, orchestrator, mock_file_processor, vector_store):
    """Test that removing a document cleans up both state and vectors.

    Critical: When doc is removed from Lovdata, both state and vectors must be cleaned.
    """
    state_file = tmp_path / "pipeline_state.json"
    config = PipelineConfig(
        data_dir=tmp_path,
        dataset_filter="test",
        force=False,
        limit=None,
    )

    extracted_dir = tmp_path / "extracted" / "test-dataset"
    extracted_dir.mkdir(parents=True)

    (extracted_dir / "doc1.xml").write_text("<doc>Content 1</doc>")
    (extracted_dir / "doc2.xml").write_text("<doc>Content 2</doc>")

    from unittest.mock import patch, Mock
    from lovdata_pipeline.domain.models import LovligFileInfo, LovligRemovedFileInfo, LovligSyncStats

    with patch("lovdata_pipeline.orchestration.pipeline_orchestrator.Lovlig") as mock_lovlig_class:
        # First run: Process both docs
        mock_lovlig1 = Mock()
        mock_lovlig1.state_file = tmp_path / "state.json"
        mock_lovlig1.state_file.touch()

        mock_lovlig1.get_changed_files.return_value = [
            LovligFileInfo(doc_id="doc1", path=extracted_dir / "doc1.xml", dataset="test", hash="hash1"),
            LovligFileInfo(doc_id="doc2", path=extracted_dir / "doc2.xml", dataset="test", hash="hash2"),
        ]
        mock_lovlig1.get_removed_files.return_value = []
        mock_lovlig1.get_all_files.return_value = []
        mock_lovlig1.sync.return_value = LovligSyncStats(added=2, modified=0, removed=0)

        mock_lovlig_class.return_value = mock_lovlig1

        result1 = orchestrator.run(config)
        assert result1.processed == 2

        # Verify both in state and have vectors
        state1 = ProcessingState(state_file)
        assert state1.is_processed("doc1", "hash1")
        assert state1.is_processed("doc2", "hash2")

        doc1_vectors = vector_store.get_chunks_by_document_id("doc1")
        doc2_vectors = vector_store.get_chunks_by_document_id("doc2")
        assert len(doc1_vectors) > 0
        assert len(doc2_vectors) > 0

        # Second run: doc2 is removed from Lovdata
        (extracted_dir / "doc2.xml").unlink()

        mock_lovlig2 = Mock()
        mock_lovlig2.state_file = tmp_path / "state.json"
        mock_lovlig2.state_file.touch()

        mock_lovlig2.get_changed_files.return_value = []
        mock_lovlig2.get_removed_files.return_value = [
            LovligRemovedFileInfo(doc_id="doc2", dataset="test"),
        ]
        mock_lovlig2.get_all_files.return_value = [
            LovligFileInfo(doc_id="doc1", path=extracted_dir / "doc1.xml", dataset="test", hash="hash1"),
        ]
        mock_lovlig2.sync.return_value = LovligSyncStats(added=0, modified=0, removed=1)

        mock_lovlig_class.return_value = mock_lovlig2

        result2 = orchestrator.run(config)
        assert result2.removed == 1

        # Verify doc2 removed from state
        state2 = ProcessingState(state_file)
        assert "doc2" not in state2.state.processed
        assert "doc2" not in state2.state.failed

        # Verify doc2 vectors cleaned up
        doc2_vectors_after = vector_store.get_chunks_by_document_id("doc2")
        assert len(doc2_vectors_after) == 0, "Removed doc should have no vectors"

        # Verify doc1 still intact
        assert state2.is_processed("doc1", "hash1")
        doc1_vectors_after = vector_store.get_chunks_by_document_id("doc1")
        assert len(doc1_vectors_after) > 0, "Remaining doc should keep vectors"


def test_state_atomic_saves(tmp_path):
    """Test that state saves are atomic (no partial writes).

    Simulates crash during save - should either have old or new state, not corrupted.
    """
    state_file = tmp_path / "pipeline_state.json"
    state = ProcessingState(state_file)

    # Initial state
    state.mark_processed("doc1", "hash1")
    state.save()

    # Verify saved
    assert state_file.exists()
    initial_content = state_file.read_text()
    initial_data = json.loads(initial_content)
    assert "doc1" in initial_data["processed"]

    # Modify and save
    state.mark_processed("doc2", "hash2")
    state.save()

    # Verify atomic write created tmp file first
    assert not (tmp_path / "pipeline_state.tmp").exists()  # tmp file cleaned up

    # Verify final state is complete
    final_content = state_file.read_text()
    final_data = json.loads(final_content)
    assert "doc1" in final_data["processed"]
    assert "doc2" in final_data["processed"]

    # Verify it's valid JSON (not corrupted)
    reloaded_state = ProcessingState(state_file)
    assert reloaded_state.is_processed("doc1", "hash1")
    assert reloaded_state.is_processed("doc2", "hash2")


def test_state_handles_rapid_sequential_saves(tmp_path):
    """Test that rapid saves don't corrupt state.

    Simulates processing many files quickly with frequent saves.
    """
    state_file = tmp_path / "pipeline_state.json"
    state = ProcessingState(state_file)

    # Rapidly save 100 documents
    for i in range(100):
        state.mark_processed(f"doc{i}", f"hash{i}")
        state.save()  # Save after each (expensive but safe)

    # Verify all saved correctly
    reloaded_state = ProcessingState(state_file)
    for i in range(100):
        assert reloaded_state.is_processed(f"doc{i}", f"hash{i}")

    assert len(reloaded_state.state.processed) == 100


def test_state_handles_mixed_success_and_failure(tmp_path):
    """Test state with documents in various states (processed, failed, removed).

    Ensures state correctly tracks complex scenarios.
    """
    state_file = tmp_path / "pipeline_state.json"
    state = ProcessingState(state_file)

    # Mixed operations
    state.mark_processed("doc1", "hash1")  # Success
    state.mark_failed("doc2", "hash2", "Parse error")  # Failure
    state.mark_processed("doc3", "hash3")  # Success
    state.mark_failed("doc4", "hash4", "Network error")  # Failure
    state.mark_processed("doc5", "hash5")  # Success

    # Now doc2 succeeds on retry
    state.mark_processed("doc2", "hash2")

    # Doc3 is removed
    state.remove("doc3")

    state.save()

    # Verify final state
    reloaded_state = ProcessingState(state_file)

    # Processed
    assert reloaded_state.is_processed("doc1", "hash1")
    assert reloaded_state.is_processed("doc2", "hash2")  # Moved from failed
    assert "doc3" not in reloaded_state.state.processed  # Removed
    assert reloaded_state.is_processed("doc5", "hash5")

    # Failed
    assert "doc2" not in reloaded_state.state.failed  # No longer failed
    assert "doc4" in reloaded_state.state.failed  # Still failed

    # Stats
    stats = reloaded_state.stats()
    assert stats["processed"] == 3  # doc1, doc2, doc5
    assert stats["failed"] == 1  # doc4
