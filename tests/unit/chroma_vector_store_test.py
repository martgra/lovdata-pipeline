"""Tests for ChromaDB vector store."""

import chromadb
import pytest

from lovdata_pipeline.domain.models import EnrichedChunk
from lovdata_pipeline.infrastructure.chroma_vector_store import ChromaVectorStoreRepository


@pytest.fixture
def temp_chroma_client(tmp_path):
    """Create temporary ChromaDB client."""
    client = chromadb.PersistentClient(path=str(tmp_path / "chroma"))
    return client


@pytest.fixture
def chroma_collection(temp_chroma_client):
    """Create ChromaDB collection."""
    return temp_chroma_client.get_or_create_collection(
        name="test_legal_docs",
        metadata={"description": "Test collection"},
    )


@pytest.fixture
def chroma_store(chroma_collection):
    """Create ChromaVectorStoreRepository."""
    return ChromaVectorStoreRepository(chroma_collection)


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
            embedded_at="2025-11-22T12:00:00Z",
        )
        chunks.append(chunk)
    return chunks


def test_chroma_store_initialization(chroma_store):
    """Test ChromaDB store initialization."""
    assert chroma_store._collection is not None
    assert chroma_store.count() == 0


def test_upsert_chunks(chroma_store, sample_chunks):
    """Test upserting chunks."""
    # Upsert chunks
    chroma_store.upsert_chunks(sample_chunks)

    # Verify count
    assert chroma_store.count() == 3

    # Verify chunks can be retrieved
    result = chroma_store._collection.get(
        ids=["doc1_chunk_0", "doc1_chunk_1", "doc1_chunk_2"],
    )
    assert len(result["ids"]) == 3


def test_delete_by_document_id(chroma_store, sample_chunks):
    """Test deleting chunks by document ID."""
    # Insert chunks from two documents
    chroma_store.upsert_chunks(sample_chunks)

    other_chunks = [
        EnrichedChunk(
            chunk_id="doc2_chunk_0",
            document_id="doc2",
            dataset_name="test-dataset",
            content="Other content",
            token_count=10,
            source_hash="def456",
            embedding=[0.7, 0.8, 0.9],
            embedding_model="test-model",
            embedded_at="2025-11-22T12:00:00Z",
        )
    ]
    chroma_store.upsert_chunks(other_chunks)

    # Verify both documents exist
    assert chroma_store.count() == 4

    # Delete doc1
    deleted = chroma_store.delete_by_document_id("doc1")
    assert deleted == 3

    # Verify only doc2 remains
    assert chroma_store.count() == 1

    result = chroma_store._collection.get()
    remaining_doc_ids = [meta["document_id"] for meta in result["metadatas"]]
    assert remaining_doc_ids == ["doc2"]


def test_get_all_document_ids(chroma_store):
    """Test getting all unique document IDs."""
    # Insert chunks from multiple documents
    chunks = [
        EnrichedChunk(
            chunk_id=f"doc{doc_num}_chunk_{chunk_num}",
            document_id=f"doc{doc_num}",
            content=f"Content {doc_num}-{chunk_num}",
            token_count=10,
            source_hash=f"hash{doc_num}",
            embedding=[0.1 * doc_num],
            embedding_model="test",
            embedded_at="2025-11-22T12:00:00Z",
        )
        for doc_num in range(1, 4)
        for chunk_num in range(2)
    ]
    chroma_store.upsert_chunks(chunks)

    # Get all document IDs
    doc_ids = chroma_store.get_all_document_ids()

    assert len(doc_ids) == 3
    assert doc_ids == {"doc1", "doc2", "doc3"}


def test_get_all_document_ids_empty_store(chroma_store):
    """Test getting document IDs from empty store."""
    doc_ids = chroma_store.get_all_document_ids()
    assert len(doc_ids) == 0
    assert doc_ids == set()


def test_get_all_document_ids_deduplicates(chroma_store):
    """Test that multiple chunks for same document return one ID."""
    # Insert many chunks for same document
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
        for i in range(10)
    ]
    chroma_store.upsert_chunks(chunks)

    # Should return only one unique document ID
    doc_ids = chroma_store.get_all_document_ids()
    assert len(doc_ids) == 1
    assert doc_ids == {"doc1"}


def test_count(chroma_store, sample_chunks):
    """Test counting chunks."""
    assert chroma_store.count() == 0

    chroma_store.upsert_chunks(sample_chunks)
    assert chroma_store.count() == 3

    # Add more chunks
    more_chunks = [
        EnrichedChunk(
            chunk_id="doc2_chunk_0",
            document_id="doc2",
            content="More content",
            token_count=10,
            source_hash="def456",
            embedding=[0.4, 0.5, 0.6],
            embedding_model="test-model",
            embedded_at="2025-11-22T12:00:00Z",
        )
    ]
    chroma_store.upsert_chunks(more_chunks)
    assert chroma_store.count() == 4


def test_upsert_empty_list(chroma_store):
    """Test upserting empty list does nothing."""
    chroma_store.upsert_chunks([])
    assert chroma_store.count() == 0


def test_delete_nonexistent_document(chroma_store):
    """Test deleting nonexistent document returns 0."""
    deleted = chroma_store.delete_by_document_id("nonexistent")
    assert deleted == 0


def test_delete_empty_doc_id(chroma_store):
    """Test deleting with empty doc_id returns 0."""
    deleted = chroma_store.delete_by_document_id("")
    assert deleted == 0
