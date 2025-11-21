"""Unit tests for domain models.

Tests only custom logic in models. Pydantic validation is tested by Pydantic.
"""

from lovdata_pipeline.domain.models import EnrichedChunk, SyncStatistics


def test_sync_statistics_total_changed():
    """Test that total_changed property works correctly."""
    stats = SyncStatistics(files_added=5, files_modified=3, files_removed=2, duration_seconds=10.5)

    assert stats.total_changed == 8
    assert stats.files_added == 5
    assert stats.files_modified == 3
    assert stats.files_removed == 2


def test_enriched_chunk_metadata_converts_cross_refs_to_string():
    """Test that EnrichedChunk.metadata converts cross_refs list to comma-separated string.

    ChromaDB only accepts primitive types (str, int, float, bool) as metadata values.
    Lists must be converted to strings.
    """
    chunk = EnrichedChunk(
        chunk_id="test-chunk-1",
        document_id="test-doc",
        dataset_name="test-dataset.tar.bz2",
        content="Test content with cross references",
        token_count=10,
        embedding=[0.1, 0.2, 0.3],
        embedding_model="test-model",
        embedded_at="2024-01-01T00:00:00Z",
        source_hash="abc123",
        cross_refs=["/lov/2020/§5", "/lov/2020/§10", "/lov/2021/§3"],
    )

    metadata = chunk.metadata

    # cross_refs should be converted to comma-separated string
    assert isinstance(metadata["cross_refs"], str)
    assert metadata["cross_refs"] == "/lov/2020/§5,/lov/2020/§10,/lov/2021/§3"


def test_enriched_chunk_metadata_handles_empty_cross_refs():
    """Test that EnrichedChunk.metadata handles empty cross_refs list correctly."""
    chunk = EnrichedChunk(
        chunk_id="test-chunk-2",
        document_id="test-doc",
        dataset_name="test-dataset.tar.bz2",
        content="Test content without cross references",
        token_count=10,
        embedding=[0.1, 0.2, 0.3],
        embedding_model="test-model",
        embedded_at="2024-01-01T00:00:00Z",
        source_hash="def456",
        cross_refs=[],
    )

    metadata = chunk.metadata

    # Empty cross_refs list should become empty string, not empty list
    assert isinstance(metadata["cross_refs"], str)
    assert metadata["cross_refs"] == ""


def test_enriched_chunk_metadata_all_values_are_primitives():
    """Test that all metadata values are ChromaDB-compatible primitive types."""
    chunk = EnrichedChunk(
        chunk_id="test-chunk-3",
        document_id="test-doc",
        dataset_name="test-dataset.tar.bz2",
        content="Test content",
        token_count=42,
        section_heading="Test Section",
        absolute_address="/test/address",
        split_reason="paragraph",
        parent_chunk_id="parent-chunk",
        embedding=[0.1, 0.2, 0.3],
        embedding_model="test-model",
        embedded_at="2024-01-01T00:00:00Z",
        source_hash="ghi789",
        cross_refs=["/ref1", "/ref2"],
    )

    metadata = chunk.metadata

    # Verify all values are primitive types (str, int, float, bool, None)
    for key, value in metadata.items():
        assert isinstance(value, (str, int, float, bool, type(None))), (
            f"Metadata key '{key}' has value of type {type(value).__name__}, "
            "which is not supported by ChromaDB. Only str, int, float, bool, or None are allowed."
        )
