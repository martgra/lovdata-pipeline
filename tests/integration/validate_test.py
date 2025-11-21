"""Integration tests for state validation command."""

import json
from pathlib import Path

import pytest

from lovdata_pipeline.domain.models import EnrichedChunk
from lovdata_pipeline.domain.services.validation_service import ValidationService
from lovdata_pipeline.infrastructure.jsonl_vector_store import JsonlVectorStoreRepository
from lovdata_pipeline.state import ProcessingState


@pytest.fixture
def temp_data_dir(tmp_path):
    """Create temporary data directory structure."""
    data_dir = tmp_path / "data"
    jsonl_dir = data_dir / "jsonl_chunks"
    jsonl_dir.mkdir(parents=True)
    return data_dir


def test_get_all_document_ids_from_jsonl_store(temp_data_dir):
    """Test getting all unique document IDs from JSONL store."""
    jsonl_dir = temp_data_dir / "jsonl_chunks"
    store = JsonlVectorStoreRepository(jsonl_dir)

    # Create chunks for multiple documents with same hash
    chunks = [
        EnrichedChunk(
            chunk_id="doc1_chunk_0",
            document_id="doc1",
            content="Content 1",
            token_count=10,
            source_hash="hash1",
            embedding=[0.1, 0.2],
            embedding_model="test",
            embedded_at="2025-11-22T12:00:00Z",
        ),
        EnrichedChunk(
            chunk_id="doc1_chunk_1",
            document_id="doc1",
            content="Content 2",
            token_count=10,
            source_hash="hash1",
            embedding=[0.2, 0.3],
            embedding_model="test",
            embedded_at="2025-11-22T12:00:00Z",
        ),
        EnrichedChunk(
            chunk_id="doc2_chunk_0",
            document_id="doc2",
            content="Content 3",
            token_count=10,
            source_hash="hash2",
            embedding=[0.3, 0.4],
            embedding_model="test",
            embedded_at="2025-11-22T12:00:00Z",
        ),
    ]

    store.upsert_chunks(chunks[:2])  # doc1 in hash1
    store.upsert_chunks([chunks[2]])  # doc2 in hash2

    # Get all document IDs
    doc_ids = store.get_all_document_ids()

    assert len(doc_ids) == 2
    assert "doc1" in doc_ids
    assert "doc2" in doc_ids


def test_validate_consistent_state_and_store(temp_data_dir):
    """Test validation when state and store are consistent."""
    jsonl_dir = temp_data_dir / "jsonl_chunks"
    store = JsonlVectorStoreRepository(jsonl_dir)

    # Create and store chunks
    chunks = [
        EnrichedChunk(
            chunk_id="doc1_chunk_0",
            document_id="doc1",
            content="Content",
            token_count=10,
            source_hash="hash1",
            embedding=[0.1],
            embedding_model="test",
            embedded_at="2025-11-22T12:00:00Z",
        ),
        EnrichedChunk(
            chunk_id="doc2_chunk_0",
            document_id="doc2",
            content="Content",
            token_count=10,
            source_hash="hash2",
            embedding=[0.2],
            embedding_model="test",
            embedded_at="2025-11-22T12:00:00Z",
        ),
    ]
    store.upsert_chunks(chunks)

    # Create matching state
    state_file = temp_data_dir / "pipeline_state.json"
    state = ProcessingState(state_file)
    state.mark_processed("doc1", "hash1")
    state.mark_processed("doc2", "hash2")
    state.save()

    # Validate using service
    validation_service = ValidationService(state, store)
    result = validation_service.validate()

    assert result.is_consistent
    assert result.state_doc_count == 2
    assert result.store_doc_count == 2
    assert len(result.in_state_not_store) == 0
    assert len(result.in_store_not_state) == 0


def test_validate_detects_state_without_chunks(temp_data_dir):
    """Test validation detects documents in state but not in store."""
    jsonl_dir = temp_data_dir / "jsonl_chunks"
    store = JsonlVectorStoreRepository(jsonl_dir)

    # Create chunks for only doc1
    chunks = [
        EnrichedChunk(
            chunk_id="doc1_chunk_0",
            document_id="doc1",
            content="Content",
            token_count=10,
            source_hash="hash1",
            embedding=[0.1],
            embedding_model="test",
            embedded_at="2025-11-22T12:00:00Z",
        ),
    ]
    store.upsert_chunks(chunks)

    # State tracks both doc1 and doc2
    state_file = temp_data_dir / "pipeline_state.json"
    state = ProcessingState(state_file)
    state.mark_processed("doc1", "hash1")
    state.mark_processed("doc2", "hash2")  # doc2 has no chunks
    state.save()

    # Validate using service
    validation_service = ValidationService(state, store)
    result = validation_service.validate()

    assert not result.is_consistent
    assert result.state_doc_count == 2
    assert result.store_doc_count == 1
    assert len(result.in_state_not_store) == 1
    assert "doc2" in result.in_state_not_store
    assert len(result.in_store_not_state) == 0


def test_validate_detects_chunks_without_state(temp_data_dir):
    """Test validation detects documents in store but not in state."""
    jsonl_dir = temp_data_dir / "jsonl_chunks"
    store = JsonlVectorStoreRepository(jsonl_dir)

    # Create chunks for doc1 and doc2
    chunks = [
        EnrichedChunk(
            chunk_id="doc1_chunk_0",
            document_id="doc1",
            content="Content",
            token_count=10,
            source_hash="hash1",
            embedding=[0.1],
            embedding_model="test",
            embedded_at="2025-11-22T12:00:00Z",
        ),
        EnrichedChunk(
            chunk_id="doc2_chunk_0",
            document_id="doc2",
            content="Content",
            token_count=10,
            source_hash="hash2",
            embedding=[0.2],
            embedding_model="test",
            embedded_at="2025-11-22T12:00:00Z",
        ),
    ]
    store.upsert_chunks(chunks)

    # State only tracks doc1
    state_file = temp_data_dir / "pipeline_state.json"
    state = ProcessingState(state_file)
    state.mark_processed("doc1", "hash1")
    state.save()

    # Validate using service
    validation_service = ValidationService(state, store)
    result = validation_service.validate()

    assert not result.is_consistent
    assert result.state_doc_count == 1
    assert result.store_doc_count == 2
    assert len(result.in_state_not_store) == 0
    assert len(result.in_store_not_state) == 1
    assert "doc2" in result.in_store_not_state


def test_validate_handles_empty_store(temp_data_dir):
    """Test validation when store is empty."""
    jsonl_dir = temp_data_dir / "jsonl_chunks"
    store = JsonlVectorStoreRepository(jsonl_dir)

    # State has documents
    state_file = temp_data_dir / "pipeline_state.json"
    state = ProcessingState(state_file)
    state.mark_processed("doc1", "hash1")
    state.save()

    # Validate using service
    validation_service = ValidationService(state, store)
    result = validation_service.validate()

    assert not result.is_consistent
    assert result.store_doc_count == 0
    assert result.state_doc_count == 1
    assert result.in_state_not_store == {"doc1"}
    assert len(result.in_store_not_state) == 0


def test_validate_handles_empty_state(temp_data_dir):
    """Test validation when state is empty."""
    jsonl_dir = temp_data_dir / "jsonl_chunks"
    store = JsonlVectorStoreRepository(jsonl_dir)

    # Store has chunks
    chunks = [
        EnrichedChunk(
            chunk_id="doc1_chunk_0",
            document_id="doc1",
            content="Content",
            token_count=10,
            source_hash="hash1",
            embedding=[0.1],
            embedding_model="test",
            embedded_at="2025-11-22T12:00:00Z",
        ),
    ]
    store.upsert_chunks(chunks)

    # Empty state
    state_file = temp_data_dir / "pipeline_state.json"
    state = ProcessingState(state_file)

    # Validate using service
    validation_service = ValidationService(state, store)
    result = validation_service.validate()

    assert not result.is_consistent
    assert result.state_doc_count == 0
    assert result.store_doc_count == 1
    assert len(result.in_state_not_store) == 0
    assert result.in_store_not_state == {"doc1"}


def test_validate_multiple_chunks_per_document(temp_data_dir):
    """Test that multiple chunks for same document are counted as one document."""
    jsonl_dir = temp_data_dir / "jsonl_chunks"
    store = JsonlVectorStoreRepository(jsonl_dir)

    # Create multiple chunks for doc1
    chunks = [
        EnrichedChunk(
            chunk_id=f"doc1_chunk_{i}",
            document_id="doc1",
            content=f"Content {i}",
            token_count=10,
            source_hash="hash1",
            embedding=[0.1 * i],
            embedding_model="test",
            embedded_at="2025-11-22T12:00:00Z",
        )
        for i in range(5)
    ]
    store.upsert_chunks(chunks)

    # Get unique document IDs
    doc_ids = store.get_all_document_ids()

    assert len(doc_ids) == 1
    assert "doc1" in doc_ids
