"""Tests for pipeline_steps module - pure Python pipeline functions."""

from unittest.mock import MagicMock, Mock, patch

import pytest

from lovdata_pipeline import pipeline_steps


def test_sync_datasets_success():
    """Test sync_datasets function."""
    with patch("lovdata_pipeline.pipeline_steps.PipelineContext") as mock_ctx_class:
        mock_ctx = Mock()
        mock_ctx_class.from_settings.return_value = mock_ctx

        mock_stats = Mock()
        mock_stats.files_added = 5
        mock_stats.files_modified = 3
        mock_stats.files_removed = 1
        mock_stats.total_changed = 9
        mock_stats.duration_seconds = 10.5

        mock_ctx.lovlig_client.sync_datasets.return_value = mock_stats
        mock_ctx.lovlig_client.clean_removed_files_from_processed_state.return_value = 1

        result = pipeline_steps.sync_datasets(force_download=False)

        assert result["files_added"] == 5
        assert result["files_modified"] == 3
        assert result["files_removed"] == 1
        assert result["total_changed"] == 9
        assert result["duration_seconds"] == 10.5

        mock_ctx.lovlig_client.sync_datasets.assert_called_once_with(force_download=False)
        mock_ctx.lovlig_client.clean_removed_files_from_processed_state.assert_called_once()


def test_get_changed_file_paths_returns_paths():
    """Test get_changed_file_paths returns list of file paths."""
    with patch("lovdata_pipeline.pipeline_steps.PipelineContext") as mock_ctx_class:
        mock_ctx = Mock()
        mock_ctx_class.from_settings.return_value = mock_ctx

        mock_file1 = Mock()
        mock_file1.absolute_path = "/path/to/file1.xml"
        mock_file1.file_size_bytes = 1024

        mock_file2 = Mock()
        mock_file2.absolute_path = "/path/to/file2.xml"
        mock_file2.file_size_bytes = 2048

        mock_ctx.lovlig_client.get_unprocessed_files.return_value = [mock_file1, mock_file2]

        result = pipeline_steps.get_changed_file_paths(force_reprocess=False)

        assert len(result) == 2
        assert "/path/to/file1.xml" in result
        assert "/path/to/file2.xml" in result

        mock_ctx.lovlig_client.get_unprocessed_files.assert_called_once_with(
            stage="chunking", force_reprocess=False
        )


def test_get_changed_file_paths_empty():
    """Test get_changed_file_paths with no files."""
    with patch("lovdata_pipeline.pipeline_steps.PipelineContext") as mock_ctx_class:
        mock_ctx = Mock()
        mock_ctx_class.from_settings.return_value = mock_ctx
        mock_ctx.lovlig_client.get_unprocessed_files.return_value = []

        result = pipeline_steps.get_changed_file_paths()

        assert result == []


def test_get_removed_file_metadata():
    """Test get_removed_file_metadata returns dict list."""
    with patch("lovdata_pipeline.pipeline_steps.PipelineContext") as mock_ctx_class:
        mock_ctx = Mock()
        mock_ctx_class.from_settings.return_value = mock_ctx

        mock_removal = Mock()
        mock_removal.model_dump.return_value = {
            "file_path": "path/to/removed.xml",
            "document_id": "doc-123",
        }

        mock_ctx.lovlig_client.get_removed_files.return_value = [mock_removal]

        result = pipeline_steps.get_removed_file_metadata()

        assert len(result) == 1
        assert result[0]["file_path"] == "path/to/removed.xml"
        assert result[0]["document_id"] == "doc-123"


def test_chunk_documents_basic(tmp_path):
    """Test chunk_documents basic functionality."""
    with (
        patch("lovdata_pipeline.pipeline_steps.PipelineContext") as mock_ctx_class,
        patch("lovdata_pipeline.pipeline_steps.LovdataXMLChunker") as mock_chunker_class,
    ):
        # Setup context mock
        mock_ctx = Mock()
        mock_ctx_class.from_settings.return_value = mock_ctx

        # Setup writer mock
        mock_writer = MagicMock()
        mock_ctx.chunk_writer = mock_writer
        mock_writer.remove_chunks_for_document.return_value = 0
        mock_writer.get_file_size_mb.return_value = 1.5
        mock_writer.__enter__ = Mock(return_value=mock_writer)
        mock_writer.__exit__ = Mock(return_value=False)

        # Setup splitter mock
        mock_splitter = Mock()
        mock_ctx.splitter = mock_splitter

        # Setup lovlig client mock
        mock_ctx.lovlig_client.mark_file_processed.return_value = None

        # Setup settings mock
        mock_ctx.settings.extracted_data_dir = tmp_path

        # Setup chunker mock
        mock_chunker = Mock()
        mock_chunker_class.return_value = mock_chunker

        mock_article = Mock()
        mock_chunker.extract_articles.return_value = [mock_article]

        mock_chunk = Mock()
        mock_chunk.split_reason = "none"
        mock_splitter.split_article.return_value = [mock_chunk]

        # Run function
        result = pipeline_steps.chunk_documents([], [])

        # Verify results
        assert result["files_processed"] == 0
        assert result["total_chunks"] == 0
        assert result["output_size_mb"] == 1.5


def test_embed_chunks_no_files(tmp_path):
    """Test embed_chunks with no files to process."""
    with patch("lovdata_pipeline.pipeline_steps.PipelineContext") as mock_ctx_class:
        # Setup context mock
        mock_ctx = Mock()
        mock_ctx_class.from_settings.return_value = mock_ctx

        # Setup manifest mock
        mock_ctx.manifest.is_stage_completed.return_value = True  # All files already embedded

        # Setup chunk reader mock
        mock_ctx.chunk_reader.read_chunks.return_value = iter([])

        result = pipeline_steps.embed_chunks([], force_reembed=False)

        assert result["embedded_chunks"] == 0
        assert result["embedded_files"] == 0


def test_index_embeddings_no_chunks(tmp_path):
    """Test index_embeddings with no chunks."""
    with patch("lovdata_pipeline.pipeline_steps.PipelineContext") as mock_ctx_class:
        # Setup context mock
        mock_ctx = Mock()
        mock_ctx_class.from_settings.return_value = mock_ctx

        # Setup chroma client mock
        mock_ctx.chroma_client.delete_by_file_path.return_value = 0

        # Setup manifest mock
        mock_ctx.manifest.set_index_status.return_value = None

        # Setup lovlig client mock
        mock_ctx.lovlig_client.get_changed_files.return_value = []

        # Setup enriched chunk reader mock
        mock_enriched_reader = Mock()
        mock_ctx.get_enriched_chunk_reader.return_value = mock_enriched_reader
        mock_enriched_reader.read_chunks.return_value = iter([])

        result = pipeline_steps.index_embeddings([], [])

        assert result["indexed_chunks"] == 0
        assert result["deleted_chunks"] == 0
