"""Configure tests."""

from unittest.mock import Mock

import pytest

from lovdata_pipeline.domain.models import (
    EnrichedChunk,
    FileProcessingResult,
    LovligSyncStats,
    PipelineConfig,
)
from lovdata_pipeline.domain.services.file_processing_service import FileProcessingService
from lovdata_pipeline.domain.vector_store import VectorStoreRepository
from lovdata_pipeline.infrastructure.jsonl_vector_store import JsonlVectorStoreRepository
from lovdata_pipeline.lovlig import Lovlig


def make_test_enriched_chunk(
    chunk_id: str,
    document_id: str,
    embedding: list[float],
    content: str = "Test content",
    dataset_name: str = "",
    **kwargs,
) -> EnrichedChunk:
    """Helper to create an EnrichedChunk for testing.

    Args:
        chunk_id: Unique chunk identifier
        document_id: Document identifier
        embedding: Embedding vector
        content: Chunk text content
        dataset_name: Dataset name
        **kwargs: Additional fields to override

    Returns:
        EnrichedChunk instance
    """
    return EnrichedChunk(
        chunk_id=chunk_id,
        document_id=document_id,
        dataset_name=dataset_name,
        content=content,
        token_count=kwargs.get("token_count", 10),
        embedding=embedding,
        embedding_model=kwargs.get("embedding_model", "test-model"),
        embedded_at=kwargs.get("embedded_at", "2024-01-01T00:00:00Z"),
        **{k: v for k, v in kwargs.items() if k not in ["token_count", "embedding_model", "embedded_at"]},
    )


# ============================================================================
# Common Fixtures - Shared across integration/E2E tests
# ============================================================================


@pytest.fixture
def mock_file_processor():
    """Create mock file processor with successful default behavior."""
    processor = Mock(spec=FileProcessingService)
    processor.process_file.return_value = FileProcessingResult(
        success=True,
        chunk_count=5,
        error_message=None,
    )
    return processor


@pytest.fixture
def mock_vector_store():
    """Create mock vector store with sensible defaults."""
    store = Mock(spec=VectorStoreRepository)
    store.count.return_value = 0
    store.delete_by_document_id.return_value = 5
    return store


@pytest.fixture
def mock_lovlig(tmp_path):
    """Create mock Lovlig client with no-changes default."""
    lovlig = Mock(spec=Lovlig)
    lovlig.state_file = tmp_path / "state.json"
    lovlig.state_file.touch()

    lovlig.get_changed_files.return_value = []
    lovlig.get_removed_files.return_value = []
    lovlig.get_all_files.return_value = []
    lovlig.sync.return_value = LovligSyncStats(
        added=0,
        modified=0,
        removed=0,
    )

    return lovlig


@pytest.fixture
def pipeline_config(tmp_path):
    """Create standard test pipeline configuration."""
    return PipelineConfig(
        data_dir=tmp_path,
        dataset_filter="test",
        force=False,
        limit=None,
    )


@pytest.fixture
def vector_store(tmp_path):
    """Create real JSONL vector store for integration testing."""
    return JsonlVectorStoreRepository(tmp_path / "vectors")


@pytest.fixture
def mock_openai_client():
    """Create mock OpenAI client for embeddings."""
    client = Mock()

    def mock_embeddings_create(input, model):
        response = Mock()
        # Return different embeddings based on input
        response.data = [
            Mock(embedding=[0.1 * (i + 1)] * 384)
            for i in range(len(input))
        ]
        return response

    client.embeddings.create = mock_embeddings_create
    return client
