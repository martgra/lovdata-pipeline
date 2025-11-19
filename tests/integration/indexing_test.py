"""End-to-end test for indexing pipeline with ChromaDB.

Tests the complete flow:
1. Sync data from lovlig
2. Detect changes
3. Chunk documents
4. Embed chunks
5. Index to ChromaDB
6. Handle deletions/updates
"""

import json
from pathlib import Path

import pytest

from lovdata_pipeline.domain.models import EnrichedChunk
from lovdata_pipeline.infrastructure.chroma_client import ChromaClient
from lovdata_pipeline.infrastructure.pipeline_manifest import (
    IndexStatus,
    PipelineManifest,
    StageStatus,
)
from tests.conftest import make_test_enriched_chunk


@pytest.fixture
def temp_chroma_dir(tmp_path):
    """Create temporary ChromaDB directory."""
    chroma_dir = tmp_path / "chroma"
    chroma_dir.mkdir()
    return chroma_dir


@pytest.fixture
def chroma_client(temp_chroma_dir):
    """Create ChromaDB client with temporary storage."""
    client = ChromaClient(
        persist_directory=str(temp_chroma_dir),
        collection_name="test_legal_docs",
    )
    yield client
    # Cleanup
    client.reset()


def test_chroma_client_basic_operations(chroma_client):
    """Test basic ChromaDB operations."""
    # Create test chunks
    chunks = [
        make_test_enriched_chunk("doc-1::hash1::0", "doc-1", [0.1, 0.2, 0.3]),
        make_test_enriched_chunk("doc-1::hash1::1", "doc-1", [0.4, 0.5, 0.6]),
        make_test_enriched_chunk("doc-2::hash2::0", "doc-2", [0.7, 0.8, 0.9]),
    ]

    chroma_client.upsert(chunks)

    # Verify count
    assert chroma_client.count() == 3

    # Get vector IDs for doc-1
    doc1_ids = chroma_client.get_vector_ids(where={"document_id": "doc-1"})
    assert len(doc1_ids) == 2
    assert set(doc1_ids) == {"doc-1::hash1::0", "doc-1::hash1::1"}

    # Delete doc-1 vectors
    deleted_count = chroma_client.delete_by_metadata(where={"document_id": "doc-1"})
    assert deleted_count == 2
    assert chroma_client.count() == 1

    # Verify doc-2 still exists
    doc2_ids = chroma_client.get_vector_ids(where={"document_id": "doc-2"})
    assert len(doc2_ids) == 1


def test_chroma_client_upsert_updates(chroma_client):
    """Test that upsert updates existing vectors."""
    # Insert initial vector
    chroma_client.upsert(
        ids=["doc-1::hash1::0"],
        embeddings=[[0.1, 0.2, 0.3]],
        metadatas=[{"document_id": "doc-1", "version": 1}],
    )

    assert chroma_client.count() == 1

    # Upsert with same ID but different embedding
    chroma_client.upsert(
        ids=["doc-1::hash1::0"],
        embeddings=[[0.9, 0.8, 0.7]],
        metadatas=[{"document_id": "doc-1", "version": 2}],
    )

    # Count should still be 1 (update, not insert)
    assert chroma_client.count() == 1


def test_indexing_workflow_with_manifest(tmp_path, chroma_client):
    """Test complete indexing workflow with manifest tracking."""
    manifest_file = tmp_path / "manifest.json"
    manifest = PipelineManifest(manifest_file)

    # Simulate document processing
    doc_id = "nl-18840614-003"
    file_hash = "abc123"

    # 1. Create document in manifest
    manifest.ensure_document(
        document_id=doc_id,
        dataset_name="gjeldende-lover",
        relative_path="nl/nl-18840614-003.xml",
        file_hash=file_hash,
        file_size_bytes=5000,
    )

    # 2. Complete chunking stage
    manifest.start_stage(doc_id, file_hash, "chunking")
    manifest.complete_stage(
        doc_id,
        file_hash,
        "chunking",
        output={"chunk_count": 3},
    )

    # 3. Complete embedding stage
    manifest.start_stage(doc_id, file_hash, "embedding")
    manifest.complete_stage(
        doc_id,
        file_hash,
        "embedding",
        output={"chunk_count": 3},
    )

    # 4. Index to ChromaDB
    manifest.start_stage(doc_id, file_hash, "indexing")

    # Simulate indexing
    vector_ids = [f"{doc_id}::{file_hash}::{i}" for i in range(3)]
    embeddings = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6], [0.7, 0.8, 0.9]]
    metadatas = [
        {"document_id": doc_id, "chunk_index": i, "file_hash": file_hash} for i in range(3)
    ]

    chroma_client.upsert(ids=vector_ids, embeddings=embeddings, metadatas=metadatas)

    manifest.complete_stage(
        doc_id,
        file_hash,
        "indexing",
        output={"vector_ids": vector_ids},
    )
    manifest.set_index_status(doc_id, IndexStatus.INDEXED)

    # Verify
    assert chroma_client.count() == 3
    doc = manifest.get_document(doc_id)
    assert doc.current_version.index_status == IndexStatus.INDEXED
    assert doc.current_version.stages["indexing"].status == StageStatus.COMPLETED

    # Save and reload manifest
    manifest.save()
    loaded_manifest = PipelineManifest.load(manifest_file)
    doc = loaded_manifest.get_document(doc_id)
    assert doc.current_version.index_status == IndexStatus.INDEXED


def test_indexing_handles_document_removal(tmp_path, chroma_client):
    """Test that document removal is properly handled."""
    manifest_file = tmp_path / "manifest.json"
    manifest = PipelineManifest(manifest_file)

    # Index two documents
    for doc_num in [1, 2]:
        doc_id = f"doc-{doc_num}"
        file_hash = f"hash{doc_num}"

        manifest.ensure_document(
            document_id=doc_id,
            dataset_name="test-dataset",
            relative_path=f"path/doc-{doc_num}.xml",
            file_hash=file_hash,
            file_size_bytes=1000,
        )

        # Index vectors
        vector_ids = [f"{doc_id}::{file_hash}::{i}" for i in range(2)]
        embeddings = [[0.1 * doc_num, 0.2 * doc_num, 0.3 * doc_num]] * 2
        metadatas = [{"document_id": doc_id} for _ in range(2)]

        chroma_client.upsert(ids=vector_ids, embeddings=embeddings, metadatas=metadatas)
        manifest.set_index_status(doc_id, IndexStatus.INDEXED)

    # Verify both documents indexed
    assert chroma_client.count() == 4

    # Remove doc-1
    deleted_count = chroma_client.delete_by_metadata(where={"document_id": "doc-1"})
    assert deleted_count == 2
    manifest.set_index_status("doc-1", IndexStatus.DELETED)

    # Verify only doc-2 remains
    assert chroma_client.count() == 2
    doc2_ids = chroma_client.get_vector_ids(where={"document_id": "doc-2"})
    assert len(doc2_ids) == 2

    # Verify manifest reflects deletion
    doc1 = manifest.get_document("doc-1")
    assert doc1.current_version.index_status == IndexStatus.DELETED


def test_indexing_handles_document_update(tmp_path, chroma_client):
    """Test that document updates replace old vectors."""
    manifest_file = tmp_path / "manifest.json"
    manifest = PipelineManifest(manifest_file)

    doc_id = "doc-1"

    # Version 1
    hash_v1 = "hash_v1"
    manifest.ensure_document(
        document_id=doc_id,
        dataset_name="test-dataset",
        relative_path="path/doc.xml",
        file_hash=hash_v1,
        file_size_bytes=1000,
    )

    vector_ids_v1 = [f"{doc_id}::{hash_v1}::{i}" for i in range(2)]
    embeddings_v1 = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    metadatas_v1 = [{"document_id": doc_id, "version": 1} for _ in range(2)]

    chroma_client.upsert(ids=vector_ids_v1, embeddings=embeddings_v1, metadatas=metadatas_v1)
    manifest.set_index_status(doc_id, IndexStatus.INDEXED)

    assert chroma_client.count() == 2

    # Document is modified (new hash)
    hash_v2 = "hash_v2"
    manifest.ensure_document(
        document_id=doc_id,
        dataset_name="test-dataset",
        relative_path="path/doc.xml",
        file_hash=hash_v2,
        file_size_bytes=1200,
    )

    # Remove old vectors
    deleted_count = chroma_client.delete_by_metadata(where={"document_id": doc_id})
    assert deleted_count == 2
    assert chroma_client.count() == 0

    # Index new version (3 chunks now)
    vector_ids_v2 = [f"{doc_id}::{hash_v2}::{i}" for i in range(3)]
    embeddings_v2 = [[0.7, 0.8, 0.9], [0.1, 0.1, 0.1], [0.2, 0.2, 0.2]]
    metadatas_v2 = [{"document_id": doc_id, "version": 2} for _ in range(3)]

    chroma_client.upsert(ids=vector_ids_v2, embeddings=embeddings_v2, metadatas=metadatas_v2)
    manifest.set_index_status(doc_id, IndexStatus.INDEXED)

    # Verify new version
    assert chroma_client.count() == 3
    doc = manifest.get_document(doc_id)
    assert doc.current_version.file_hash == hash_v2
    assert len(doc.version_history) == 1
    assert doc.version_history[0].file_hash == hash_v1


def test_chroma_query_operations(chroma_client):
    """Test ChromaDB query functionality."""
    # Index some test documents
    ids = ["doc-1::hash::0", "doc-1::hash::1", "doc-2::hash::0"]
    embeddings = [
        [1.0, 0.0, 0.0],
        [0.9, 0.1, 0.0],
        [0.0, 1.0, 0.0],
    ]
    metadatas = [
        {"document_id": "doc-1", "text": "law about taxes"},
        {"document_id": "doc-1", "text": "tax regulations"},
        {"document_id": "doc-2", "text": "criminal law"},
    ]

    chroma_client.upsert(ids=ids, embeddings=embeddings, metadatas=metadatas)

    # Query similar to first document
    query_embedding = [0.95, 0.05, 0.0]
    results = chroma_client.query(query_embeddings=[query_embedding], n_results=2)

    # Should return doc-1 chunks first (closest embeddings)
    assert len(results["ids"][0]) == 2
    assert "doc-1::hash::0" in results["ids"][0]
    assert "doc-1::hash::1" in results["ids"][0]


def test_collection_info(chroma_client):
    """Test getting collection information."""
    info = chroma_client.get_collection_info()

    assert info["name"] == "test_legal_docs"
    assert info["count"] == 0
    assert "metadata" in info

    # Add some vectors
    chroma_client.upsert(
        ids=["test::1"],
        embeddings=[[0.1, 0.2, 0.3]],
        metadatas=[{"test": "data"}],
    )

    info = chroma_client.get_collection_info()
    assert info["count"] == 1


@pytest.mark.skipif(
    not pytest.importorskip("chromadb", reason="chromadb not installed"),
    reason="ChromaDB not available",
)
def test_chroma_client_import():
    """Test that ChromaDB client can be imported."""
    from lovdata_pipeline.infrastructure.chroma_client import ChromaClient

    assert ChromaClient is not None
