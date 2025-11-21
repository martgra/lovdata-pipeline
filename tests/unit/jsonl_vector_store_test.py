"""Tests for JSONL vector store."""

import tempfile
from pathlib import Path

import pytest

from lovdata_pipeline.domain.models import ChunkMetadata, EnrichedChunk
from lovdata_pipeline.infrastructure.jsonl_vector_store import JsonlVectorStoreRepository


@pytest.fixture
def temp_storage_dir():
    """Create temporary storage directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_chunks():
    """Create sample enriched chunks for testing."""
    chunks = []
    for i in range(3):
        chunk = EnrichedChunk(
            chunk_id=f"doc1_chunk_{i}",
            document_id="doc1",
            dataset_name="test-dataset",
            content=f"Test content {i}",
            token_count=10 + i,
            section_heading="Test Section",
            absolute_address=f"/test/section/{i}",
            split_reason="none",
            source_hash="abc123",
            embedding=[0.1, 0.2, 0.3],
            embedding_model="test-model",
            embedded_at="2025-11-20T12:00:00Z",
        )
        chunks.append(chunk)
    return chunks


def test_jsonl_store_initialization(temp_storage_dir):
    """Test JSONL store initialization."""
    store = JsonlVectorStoreRepository(temp_storage_dir)
    assert store._storage_dir.exists()
    assert store._storage_dir.is_dir()


def test_upsert_chunks(temp_storage_dir, sample_chunks):
    """Test upserting chunks."""
    store = JsonlVectorStoreRepository(temp_storage_dir)

    # Upsert chunks
    store.upsert_chunks(sample_chunks)

    # Verify file was created
    jsonl_file = temp_storage_dir / "abc123.jsonl"
    assert jsonl_file.exists()

    # Verify content
    with open(jsonl_file) as f:
        lines = f.readlines()
    assert len(lines) == 3


def test_upsert_updates_existing(temp_storage_dir, sample_chunks):
    """Test that upsert updates existing chunks."""
    store = JsonlVectorStoreRepository(temp_storage_dir)

    # Insert initial chunks
    store.upsert_chunks(sample_chunks)

    # Update one chunk
    updated_chunk = EnrichedChunk(
        chunk_id="doc1_chunk_0",
        document_id="doc1",
        dataset_name="test-dataset",
        content="Updated content",
        token_count=999,
        section_heading="Test Section",
        absolute_address="/test/section/0",
        split_reason="none",
        source_hash="abc123",
        embedding=[0.4, 0.5, 0.6],
        embedding_model="test-model",
        embedded_at="2025-11-20T13:00:00Z",
    )

    store.upsert_chunks([updated_chunk])

    # Verify chunk was updated
    chunks = store.get_chunks_by_hash("abc123")
    assert len(chunks) == 3

    updated = next(c for c in chunks if c.chunk_id == "doc1_chunk_0")
    assert updated.content == "Updated content"
    assert updated.token_count == 999


def test_delete_by_document_id(temp_storage_dir, sample_chunks):
    """Test deleting chunks by document ID."""
    store = JsonlVectorStoreRepository(temp_storage_dir)

    # Insert chunks
    store.upsert_chunks(sample_chunks)

    # Add chunks from another document
    other_chunks = [
        EnrichedChunk(
            chunk_id="doc2_chunk_0",
            document_id="doc2",
            dataset_name="test-dataset",
            content="Other content",
            token_count=10,
            source_hash="abc123",
            embedding=[0.7, 0.8, 0.9],
            embedding_model="test-model",
            embedded_at="2025-11-20T12:00:00Z",
        )
    ]
    store.upsert_chunks(other_chunks)

    # Delete doc1
    deleted = store.delete_by_document_id("doc1")
    assert deleted == 3

    # Verify only doc2 remains
    remaining = store.get_chunks_by_hash("abc123")
    assert len(remaining) == 1
    assert remaining[0].document_id == "doc2"


def test_delete_removes_empty_file(temp_storage_dir, sample_chunks):
    """Test that deleting all chunks removes the file."""
    store = JsonlVectorStoreRepository(temp_storage_dir)

    # Insert chunks
    store.upsert_chunks(sample_chunks)

    jsonl_file = temp_storage_dir / "abc123.jsonl"
    assert jsonl_file.exists()

    # Delete all chunks
    deleted = store.delete_by_document_id("doc1")
    assert deleted == 3

    # Verify file was deleted
    assert not jsonl_file.exists()


def test_count(temp_storage_dir, sample_chunks):
    """Test counting chunks."""
    store = JsonlVectorStoreRepository(temp_storage_dir)

    assert store.count() == 0

    store.upsert_chunks(sample_chunks)
    assert store.count() == 3


def test_get_chunks_by_hash(temp_storage_dir, sample_chunks):
    """Test retrieving chunks by hash."""
    store = JsonlVectorStoreRepository(temp_storage_dir)

    store.upsert_chunks(sample_chunks)

    chunks = store.get_chunks_by_hash("abc123")
    assert len(chunks) == 3
    assert all(c.source_hash == "abc123" for c in chunks)

    # Non-existent hash
    chunks = store.get_chunks_by_hash("nonexistent")
    assert len(chunks) == 0


def test_get_chunks_by_document_id(temp_storage_dir):
    """Test retrieving chunks by document ID."""
    store = JsonlVectorStoreRepository(temp_storage_dir)

    # Create chunks from different documents with different hashes
    chunks1 = [
        EnrichedChunk(
            chunk_id="doc1_chunk_0",
            document_id="doc1",
            content="Content 1",
            token_count=10,
            source_hash="hash1",
            embedding=[0.1, 0.2],
            embedding_model="test",
            embedded_at="2025-11-20T12:00:00Z",
        )
    ]

    chunks2 = [
        EnrichedChunk(
            chunk_id="doc2_chunk_0",
            document_id="doc2",
            content="Content 2",
            token_count=10,
            source_hash="hash2",
            embedding=[0.3, 0.4],
            embedding_model="test",
            embedded_at="2025-11-20T12:00:00Z",
        )
    ]

    store.upsert_chunks(chunks1)
    store.upsert_chunks(chunks2)

    # Get chunks for doc1
    doc1_chunks = store.get_chunks_by_document_id("doc1")
    assert len(doc1_chunks) == 1
    assert doc1_chunks[0].document_id == "doc1"


def test_list_hashes(temp_storage_dir, sample_chunks):
    """Test listing all hashes."""
    store = JsonlVectorStoreRepository(temp_storage_dir)

    # Create chunks with different hashes
    store.upsert_chunks(sample_chunks)  # hash: abc123

    other_chunks = [
        EnrichedChunk(
            chunk_id="doc2_chunk_0",
            document_id="doc2",
            content="Other",
            token_count=10,
            source_hash="xyz789",
            embedding=[0.5],
            embedding_model="test",
            embedded_at="2025-11-20T12:00:00Z",
        )
    ]
    store.upsert_chunks(other_chunks)

    hashes = store.list_hashes()
    assert len(hashes) == 2
    assert "abc123" in hashes
    assert "xyz789" in hashes


def test_multiple_documents_same_hash(temp_storage_dir):
    """Test handling multiple documents with the same source hash."""
    store = JsonlVectorStoreRepository(temp_storage_dir)

    # Two documents chunked from the same source file (same hash)
    chunks1 = [
        EnrichedChunk(
            chunk_id="doc1_chunk_0",
            document_id="doc1",
            content="Doc1 content",
            token_count=10,
            source_hash="shared_hash",
            embedding=[0.1],
            embedding_model="test",
            embedded_at="2025-11-20T12:00:00Z",
        )
    ]

    chunks2 = [
        EnrichedChunk(
            chunk_id="doc2_chunk_0",
            document_id="doc2",
            content="Doc2 content",
            token_count=10,
            source_hash="shared_hash",
            embedding=[0.2],
            embedding_model="test",
            embedded_at="2025-11-20T12:00:00Z",
        )
    ]

    store.upsert_chunks(chunks1)
    store.upsert_chunks(chunks2)

    # Both should be in the same file
    all_chunks = store.get_chunks_by_hash("shared_hash")
    assert len(all_chunks) == 2

    # Should have only one file
    hashes = store.list_hashes()
    assert len(hashes) == 1
