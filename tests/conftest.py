"""Configure tests."""

from lovdata_pipeline.domain.models import EnrichedChunk


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
