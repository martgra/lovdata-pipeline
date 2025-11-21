"""Integration tests for storage migration between ChromaDB and JSONL.

Tests that migration correctly handles the metadata format differences,
especially cross_refs which is stored as a string in ChromaDB and a list in JSONL.
"""

from pathlib import Path

import chromadb
import pytest

from lovdata_pipeline.domain.models import EnrichedChunk
from lovdata_pipeline.infrastructure.chroma_vector_store import ChromaVectorStoreRepository
from lovdata_pipeline.infrastructure.jsonl_vector_store import JsonlVectorStoreRepository


@pytest.fixture
def test_chunks():
    """Create test chunks with cross_refs."""
    return [
        EnrichedChunk(
            chunk_id="test-chunk-1",
            document_id="test-doc-1",
            dataset_name="test-dataset.tar.bz2",
            content="Test content with multiple cross references",
            token_count=10,
            section_heading="§1",
            absolute_address="/lov/2020/§1",
            source_hash="hash1",
            cross_refs=["/lov/2020/§5", "/lov/2020/§10", "/lov/2021/§3"],
            embedding=[0.1, 0.2, 0.3],
            embedding_model="test-model",
            embedded_at="2024-01-01T00:00:00Z",
        ),
        EnrichedChunk(
            chunk_id="test-chunk-2",
            document_id="test-doc-2",
            dataset_name="test-dataset.tar.bz2",
            content="Test content without cross references",
            token_count=8,
            section_heading="§2",
            absolute_address="/lov/2020/§2",
            source_hash="hash2",
            cross_refs=[],
            embedding=[0.4, 0.5, 0.6],
            embedding_model="test-model",
            embedded_at="2024-01-01T00:00:00Z",
        ),
    ]


def test_jsonl_to_chroma_migration_preserves_cross_refs(tmp_path, test_chunks):
    """Test migration from JSONL to ChromaDB preserves cross_refs correctly.

    JSONL stores cross_refs as a list, ChromaDB converts it to a comma-separated string.
    """
    jsonl_path = tmp_path / "jsonl_chunks"
    chroma_path = tmp_path / "chroma"

    # Write to JSONL
    jsonl_store = JsonlVectorStoreRepository(jsonl_path)
    jsonl_store.upsert_chunks(test_chunks)

    # Read from JSONL and write to ChromaDB
    client = chromadb.PersistentClient(path=str(chroma_path))
    collection = client.get_or_create_collection(
        name="legal_docs",
        metadata={"description": "Test migration"},
    )
    chroma_store = ChromaVectorStoreRepository(collection)

    # Migrate
    chunks_from_jsonl = jsonl_store.get_chunks_by_hash("hash1")
    chroma_store.upsert_chunks(chunks_from_jsonl)

    # Verify in ChromaDB
    result = collection.get(ids=["test-chunk-1"], include=["metadatas"])

    # ChromaDB should have cross_refs as comma-separated string
    assert result["metadatas"][0]["cross_refs"] == "/lov/2020/§5,/lov/2020/§10,/lov/2021/§3"
    assert isinstance(result["metadatas"][0]["cross_refs"], str)


def test_chroma_to_jsonl_migration_converts_cross_refs_to_list(tmp_path, test_chunks):
    """Test migration from ChromaDB to JSONL converts cross_refs string back to list.

    ChromaDB stores cross_refs as string, JSONL should restore it as a list.
    """
    jsonl_path = tmp_path / "jsonl_chunks"
    chroma_path = tmp_path / "chroma"

    # Write to ChromaDB
    client = chromadb.PersistentClient(path=str(chroma_path))
    collection = client.get_or_create_collection(
        name="legal_docs",
        metadata={"description": "Test migration"},
    )
    chroma_store = ChromaVectorStoreRepository(collection)
    chroma_store.upsert_chunks(test_chunks)

    # Read from ChromaDB (simulating migration logic)
    result = collection.get(
        ids=["test-chunk-1"],
        include=["embeddings", "metadatas", "documents"],
    )

    # Convert cross_refs string back to list (this is what migrate command does)
    cross_refs_raw = result["metadatas"][0].get("cross_refs", "")
    if isinstance(cross_refs_raw, str):
        cross_refs = [ref.strip() for ref in cross_refs_raw.split(",") if ref.strip()]
    else:
        cross_refs = cross_refs_raw if cross_refs_raw else []

    # Create EnrichedChunk with converted cross_refs
    migrated_chunk = EnrichedChunk(
        chunk_id=result["ids"][0],
        document_id=result["metadatas"][0]["document_id"],
        dataset_name=result["metadatas"][0]["dataset_name"],
        content=result["documents"][0],
        token_count=int(result["metadatas"][0]["token_count"]),
        section_heading=result["metadatas"][0]["section_heading"],
        absolute_address=result["metadatas"][0]["absolute_address"],
        source_hash=result["metadatas"][0]["source_hash"],
        cross_refs=cross_refs,
        embedding=list(result["embeddings"][0]),
        embedding_model=result["metadatas"][0]["embedding_model"],
        embedded_at=result["metadatas"][0]["embedded_at"],
    )

    # Verify cross_refs is restored as list
    assert isinstance(migrated_chunk.cross_refs, list)
    assert migrated_chunk.cross_refs == ["/lov/2020/§5", "/lov/2020/§10", "/lov/2021/§3"]

    # Write to JSONL
    jsonl_store = JsonlVectorStoreRepository(jsonl_path)
    jsonl_store.upsert_chunks([migrated_chunk])

    # Read back and verify
    chunks_from_jsonl = jsonl_store.get_chunks_by_hash(test_chunks[0].source_hash)
    assert len(chunks_from_jsonl) == 1
    assert isinstance(chunks_from_jsonl[0].cross_refs, list)
    assert chunks_from_jsonl[0].cross_refs == ["/lov/2020/§5", "/lov/2020/§10", "/lov/2021/§3"]


def test_migration_handles_empty_cross_refs(tmp_path, test_chunks):
    """Test migration correctly handles empty cross_refs."""
    jsonl_path = tmp_path / "jsonl_chunks"
    chroma_path = tmp_path / "chroma"

    # Get chunk with empty cross_refs
    empty_cross_refs_chunk = test_chunks[1]

    # Write to ChromaDB
    client = chromadb.PersistentClient(path=str(chroma_path))
    collection = client.get_or_create_collection(
        name="legal_docs",
        metadata={"description": "Test migration"},
    )
    chroma_store = ChromaVectorStoreRepository(collection)
    chroma_store.upsert_chunks([empty_cross_refs_chunk])

    # Read from ChromaDB
    result = collection.get(
        ids=["test-chunk-2"],
        include=["embeddings", "metadatas", "documents"],
    )

    # ChromaDB should have empty string
    assert result["metadatas"][0]["cross_refs"] == ""

    # Convert back to list
    cross_refs_raw = result["metadatas"][0].get("cross_refs", "")
    if isinstance(cross_refs_raw, str):
        cross_refs = [ref.strip() for ref in cross_refs_raw.split(",") if ref.strip()]
    else:
        cross_refs = cross_refs_raw if cross_refs_raw else []

    # Should be empty list, not list with empty string
    assert cross_refs == []
