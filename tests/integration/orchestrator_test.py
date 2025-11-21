"""Integration tests for PipelineOrchestrator.

Tests the complete pipeline workflow: sync → identify → process → cleanup.
This covers the critical orchestration logic that was previously untested.
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from lovdata_pipeline.domain.models import (
    FileInfo,
    FileProcessingResult,
    LovligFileInfo,
    LovligRemovedFileInfo,
    LovligSyncStats,
    PipelineConfig,
)
from lovdata_pipeline.domain.services.file_processing_service import FileProcessingService
from lovdata_pipeline.domain.vector_store import VectorStoreRepository
from lovdata_pipeline.lovlig import Lovlig
from lovdata_pipeline.orchestration.pipeline_orchestrator import PipelineOrchestrator
from lovdata_pipeline.progress import NoOpProgressTracker
from lovdata_pipeline.state import ProcessingState


# Local fixture for orchestrator (combines mocks)
@pytest.fixture
def orchestrator(mock_file_processor, mock_vector_store):
    """Create orchestrator with mocked dependencies."""
    return PipelineOrchestrator(
        file_processor=mock_file_processor,
        vector_store=mock_vector_store,
    )


class TestPipelineOrchestrator:
    """Tests for PipelineOrchestrator main workflow."""

    @patch("lovdata_pipeline.orchestration.pipeline_orchestrator.Lovlig")
    def test_orchestrator_runs_full_pipeline(
        self, mock_lovlig_class, orchestrator, pipeline_config, mock_lovlig
    ):
        """Test orchestrator runs all pipeline stages successfully."""
        mock_lovlig_class.return_value = mock_lovlig

        result = orchestrator.run(pipeline_config)

        # Verify all stages were called
        mock_lovlig.sync.assert_called_once_with(force=False)
        mock_lovlig.get_changed_files.assert_called_once()
        mock_lovlig.get_removed_files.assert_called_once()

        # Verify result structure
        assert result.processed == 0
        assert result.failed == 0
        assert result.removed == 0

    @patch("lovdata_pipeline.orchestration.pipeline_orchestrator.Lovlig")
    def test_orchestrator_processes_changed_files(
        self, mock_lovlig_class, orchestrator, pipeline_config, mock_lovlig, mock_file_processor
    ):
        """Test orchestrator processes changed files."""
        mock_lovlig_class.return_value = mock_lovlig

        # Setup: 2 changed files
        mock_lovlig.get_changed_files.return_value = [
            LovligFileInfo(
                doc_id="doc1",
                path=Path("/data/doc1.xml"),
                hash="hash1",
                dataset="test",
            ),
            LovligFileInfo(
                doc_id="doc2",
                path=Path("/data/doc2.xml"),
                hash="hash2",
                dataset="test",
            ),
        ]

        result = orchestrator.run(pipeline_config)

        # Verify both files were processed
        assert mock_file_processor.process_file.call_count == 2
        assert result.processed == 2
        assert result.failed == 0

    @patch("lovdata_pipeline.orchestration.pipeline_orchestrator.Lovlig")
    def test_orchestrator_skips_already_processed_files(
        self, mock_lovlig_class, orchestrator, pipeline_config, mock_lovlig, mock_file_processor, tmp_path
    ):
        """Test orchestrator skips files that are already processed."""
        mock_lovlig_class.return_value = mock_lovlig

        # Pre-populate state with processed file
        state = ProcessingState(tmp_path / "pipeline_state.json")
        state.mark_processed("doc1", "hash1")
        state.save()

        # Setup: 2 files, one already processed
        mock_lovlig.get_changed_files.return_value = [
            LovligFileInfo(
                doc_id="doc1",
                path=Path("/data/doc1.xml"),
                hash="hash1",  # Same hash as in state
                dataset="test",
            ),
            LovligFileInfo(
                doc_id="doc2",
                path=Path("/data/doc2.xml"),
                hash="hash2",
                dataset="test",
            ),
        ]

        result = orchestrator.run(pipeline_config)

        # Only doc2 should be processed (doc1 skipped)
        assert mock_file_processor.process_file.call_count == 1
        assert result.processed == 1

    @patch("lovdata_pipeline.orchestration.pipeline_orchestrator.Lovlig")
    def test_orchestrator_reprocesses_on_hash_change(
        self, mock_lovlig_class, orchestrator, pipeline_config, mock_lovlig, mock_file_processor, tmp_path
    ):
        """Test orchestrator reprocesses files when hash changes."""
        mock_lovlig_class.return_value = mock_lovlig

        # Pre-populate state with old hash
        state = ProcessingState(tmp_path / "pipeline_state.json")
        state.mark_processed("doc1", "old_hash")
        state.save()

        # Setup: File with new hash
        mock_lovlig.get_changed_files.return_value = [
            LovligFileInfo(
                doc_id="doc1",
                path=Path("/data/doc1.xml"),
                hash="new_hash",  # Hash changed
                dataset="test",
            ),
        ]

        result = orchestrator.run(pipeline_config)

        # File should be reprocessed due to hash change
        assert mock_file_processor.process_file.call_count == 1
        assert result.processed == 1

    @patch("lovdata_pipeline.orchestration.pipeline_orchestrator.Lovlig")
    def test_orchestrator_force_reprocesses_all(
        self, mock_lovlig_class, orchestrator, pipeline_config, mock_lovlig, mock_file_processor, tmp_path
    ):
        """Test orchestrator force flag reprocesses all files."""
        mock_lovlig_class.return_value = mock_lovlig

        # Pre-populate state
        state = ProcessingState(tmp_path / "pipeline_state.json")
        state.mark_processed("doc1", "hash1")
        state.mark_processed("doc2", "hash2")
        state.save()

        # Setup: All files (not just changed)
        mock_lovlig.get_all_files.return_value = [
            LovligFileInfo(
                doc_id="doc1",
                path=Path("/data/doc1.xml"),
                hash="hash1",
                dataset="test",
            ),
            LovligFileInfo(
                doc_id="doc2",
                path=Path("/data/doc2.xml"),
                hash="hash2",
                dataset="test",
            ),
        ]

        # Enable force mode
        pipeline_config.force = True

        result = orchestrator.run(pipeline_config)

        # Both files should be reprocessed despite being in state
        assert mock_file_processor.process_file.call_count == 2
        assert result.processed == 2

    @patch("lovdata_pipeline.orchestration.pipeline_orchestrator.Lovlig")
    def test_orchestrator_handles_processing_failures(
        self, mock_lovlig_class, orchestrator, pipeline_config, mock_lovlig, mock_file_processor
    ):
        """Test orchestrator handles file processing failures gracefully."""
        mock_lovlig_class.return_value = mock_lovlig

        # Setup: One file that will fail
        mock_lovlig.get_changed_files.return_value = [
            LovligFileInfo(
                doc_id="doc1",
                path=Path("/data/doc1.xml"),
                hash="hash1",
                dataset="test",
            ),
        ]

        # Make processing fail
        mock_file_processor.process_file.return_value = FileProcessingResult(
            success=False,
            chunk_count=0,
            error_message="Parse error: Invalid XML",
        )

        result = orchestrator.run(pipeline_config)

        # Should record failure
        assert result.processed == 0
        assert result.failed == 1

        # Verify failure was saved to state
        state = ProcessingState(pipeline_config.data_dir / "pipeline_state.json")
        assert "doc1" in state.state.failed

    @patch("lovdata_pipeline.orchestration.pipeline_orchestrator.Lovlig")
    def test_orchestrator_retries_previously_failed_files(
        self, mock_lovlig_class, orchestrator, pipeline_config, mock_lovlig, mock_file_processor, tmp_path
    ):
        """Test orchestrator retries files that previously failed."""
        mock_lovlig_class.return_value = mock_lovlig

        # Pre-populate state with failed file
        state = ProcessingState(tmp_path / "pipeline_state.json")
        state.mark_failed("doc1", "hash1", "Previous error")
        state.save()

        # Setup: Same file appears in changed files
        mock_lovlig.get_changed_files.return_value = [
            LovligFileInfo(
                doc_id="doc1",
                path=Path("/data/doc1.xml"),
                hash="hash1",
                dataset="test",
            ),
        ]

        # This time it succeeds
        mock_file_processor.process_file.return_value = FileProcessingResult(
            success=True,
            chunk_count=3,
            error_message=None,
        )

        result = orchestrator.run(pipeline_config)

        # File should be retried and succeed
        assert result.processed == 1
        assert result.failed == 0

        # Verify failure was removed from state
        state = ProcessingState(pipeline_config.data_dir / "pipeline_state.json")
        assert "doc1" not in state.state.failed
        assert "doc1" in state.state.processed

    @patch("lovdata_pipeline.orchestration.pipeline_orchestrator.Lovlig")
    def test_orchestrator_removes_deleted_files(
        self, mock_lovlig_class, orchestrator, pipeline_config, mock_lovlig, mock_vector_store, tmp_path
    ):
        """Test orchestrator cleans up removed files from vector store."""
        mock_lovlig_class.return_value = mock_lovlig

        # Pre-populate state with processed file
        state = ProcessingState(tmp_path / "pipeline_state.json")
        state.mark_processed("doc1", "hash1")
        state.save()

        # Setup: File was removed
        mock_lovlig.get_removed_files.return_value = [
            LovligRemovedFileInfo(
                doc_id="doc1",
                dataset="test",
            ),
        ]

        result = orchestrator.run(pipeline_config)

        # Verify vector store cleanup was called
        mock_vector_store.delete_by_document_id.assert_called_once_with("doc1")
        assert result.removed == 1

        # Verify file was removed from state
        state = ProcessingState(pipeline_config.data_dir / "pipeline_state.json")
        assert "doc1" not in state.state.processed

    @patch("lovdata_pipeline.orchestration.pipeline_orchestrator.Lovlig")
    def test_orchestrator_respects_limit_parameter(
        self, mock_lovlig_class, orchestrator, pipeline_config, mock_lovlig, mock_file_processor
    ):
        """Test orchestrator respects file processing limit."""
        mock_lovlig_class.return_value = mock_lovlig

        # Setup: 5 changed files
        mock_lovlig.get_changed_files.return_value = [
            LovligFileInfo(
                doc_id=f"doc{i}",
                path=Path(f"/data/doc{i}.xml"),
                hash=f"hash{i}",
                dataset="test",
            )
            for i in range(1, 6)
        ]

        # Set limit to 2
        pipeline_config.limit = 2

        result = orchestrator.run(pipeline_config)

        # Only 2 files should be processed
        assert mock_file_processor.process_file.call_count == 2
        assert result.processed == 2

    @patch("lovdata_pipeline.orchestration.pipeline_orchestrator.Lovlig")
    def test_orchestrator_validates_vector_store_connection(
        self, mock_lovlig_class, orchestrator, pipeline_config, mock_lovlig, mock_vector_store
    ):
        """Test orchestrator validates vector store connection before processing."""
        mock_lovlig_class.return_value = mock_lovlig

        # Make vector store connection fail
        mock_vector_store.count.side_effect = RuntimeError("Connection failed")

        with pytest.raises(RuntimeError, match="Vector store connection failed"):
            orchestrator.run(pipeline_config)

    @patch("lovdata_pipeline.orchestration.pipeline_orchestrator.Lovlig")
    def test_orchestrator_validates_lovlig_state_created(
        self, mock_lovlig_class, orchestrator, pipeline_config, mock_lovlig, tmp_path
    ):
        """Test orchestrator validates lovlig state file was created."""
        mock_lovlig_class.return_value = mock_lovlig

        # Remove state file (simulate sync failure)
        mock_lovlig.state_file = tmp_path / "nonexistent_state.json"

        with pytest.raises(RuntimeError, match="Lovlig state file not created"):
            orchestrator.run(pipeline_config)

    @patch("lovdata_pipeline.orchestration.pipeline_orchestrator.Lovlig")
    def test_orchestrator_handles_empty_dataset(
        self, mock_lovlig_class, orchestrator, pipeline_config, mock_lovlig
    ):
        """Test orchestrator handles case with no files to process."""
        mock_lovlig_class.return_value = mock_lovlig

        # No changed files, no removed files
        result = orchestrator.run(pipeline_config)

        assert result.processed == 0
        assert result.failed == 0
        assert result.removed == 0

    @patch("lovdata_pipeline.orchestration.pipeline_orchestrator.Lovlig")
    def test_orchestrator_uses_noop_tracker_by_default(
        self, mock_lovlig_class, orchestrator, pipeline_config, mock_lovlig
    ):
        """Test orchestrator uses NoOpProgressTracker when none provided."""
        mock_lovlig_class.return_value = mock_lovlig

        # Should not raise even without progress tracker
        result = orchestrator.run(pipeline_config)

        assert isinstance(result.processed, int)

    @patch("lovdata_pipeline.orchestration.pipeline_orchestrator.Lovlig")
    def test_orchestrator_accepts_custom_progress_tracker(
        self, mock_lovlig_class, orchestrator, pipeline_config, mock_lovlig
    ):
        """Test orchestrator accepts custom progress tracker."""
        mock_lovlig_class.return_value = mock_lovlig

        tracker = Mock()
        tracker.start_stage = Mock()
        tracker.end_stage = Mock()
        tracker.show_summary = Mock()

        result = orchestrator.run(pipeline_config, progress_tracker=tracker)

        # Verify tracker was used
        assert tracker.start_stage.call_count >= 1
        tracker.show_summary.assert_called_once()

    @patch("lovdata_pipeline.orchestration.pipeline_orchestrator.Lovlig")
    def test_orchestrator_saves_state_after_each_file(
        self, mock_lovlig_class, orchestrator, pipeline_config, mock_lovlig, mock_file_processor, tmp_path
    ):
        """Test orchestrator saves state after processing each file."""
        mock_lovlig_class.return_value = mock_lovlig

        # Setup: 2 files
        mock_lovlig.get_changed_files.return_value = [
            LovligFileInfo(
                doc_id="doc1",
                path=Path("/data/doc1.xml"),
                hash="hash1",
                dataset="test",
            ),
            LovligFileInfo(
                doc_id="doc2",
                path=Path("/data/doc2.xml"),
                hash="hash2",
                dataset="test",
            ),
        ]

        # Make first file succeed, second fail
        mock_file_processor.process_file.side_effect = [
            FileProcessingResult(success=True, chunk_count=3, error_message=None),
            FileProcessingResult(success=False, chunk_count=0, error_message="Error"),
        ]

        result = orchestrator.run(pipeline_config)

        # Verify state was saved
        state = ProcessingState(pipeline_config.data_dir / "pipeline_state.json")
        assert "doc1" in state.state.processed
        assert "doc2" in state.state.failed

    @patch("lovdata_pipeline.orchestration.pipeline_orchestrator.Lovlig")
    def test_orchestrator_handles_removal_cleanup_errors(
        self, mock_lovlig_class, orchestrator, pipeline_config, mock_lovlig, mock_vector_store
    ):
        """Test orchestrator handles errors during removal cleanup gracefully."""
        mock_lovlig_class.return_value = mock_lovlig

        # Setup: File removal
        mock_lovlig.get_removed_files.return_value = [
            LovligRemovedFileInfo(
                doc_id="doc1",
                dataset="test",
            ),
        ]

        # Make vector store deletion fail
        mock_vector_store.delete_by_document_id.side_effect = Exception("Delete failed")

        # Should not raise, but log warning
        result = orchestrator.run(pipeline_config)

        # Pipeline should continue despite deletion error
        assert isinstance(result.removed, int)
