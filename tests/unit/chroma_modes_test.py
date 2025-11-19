"""Unit tests for ChromaDB mode configuration."""

import pytest

from lovdata_pipeline.infrastructure.chroma_client import ChromaClient
from tests.conftest import make_test_enriched_chunk


def test_memory_mode():
    """Test in-memory ephemeral mode."""
    client = ChromaClient(mode="memory", collection_name="test")
    assert client.mode == "memory"
    assert client.collection_name == "test"


def test_persistent_mode(tmp_path):
    """Test persistent local storage mode."""
    test_dir = tmp_path / "chroma_test"
    client = ChromaClient(
        mode="persistent",
        persist_directory=str(test_dir),
        collection_name="test"
    )
    assert client.mode == "persistent"
    assert client.persist_directory == str(test_dir)


def test_client_mode_fails_without_server():
    """Test client mode fails gracefully without server running."""
    # Client mode will fail during initialization if server not available
    with pytest.raises(ValueError):
        ChromaClient(
            mode="client",
            host="nonexistent",
            port=9999,
            collection_name="test"
        )


def test_invalid_mode():
    """Test that invalid mode raises ValueError."""
    with pytest.raises(ValueError, match="Invalid mode"):
        ChromaClient(mode="invalid_mode")


def test_mode_operations():
    """Test basic operations work in memory mode."""
    client = ChromaClient(mode="memory", collection_name="test_ops")

    # Upsert
    client.upsert(
        ids=["doc1::v1::0"],
        embeddings=[[0.1, 0.2, 0.3]],
        metadatas=[{"document_id": "doc1"}]
    )

    # Get vector IDs
    vector_ids = client.get_vector_ids(where={"document_id": "doc1"})
    assert len(vector_ids) == 1

    # Get collection info
    info = client.get_collection_info()
    assert info["count"] == 1

    # Delete
    client.delete(ids=vector_ids)

    # Verify deletion
    info = client.get_collection_info()
    assert info["count"] == 0
