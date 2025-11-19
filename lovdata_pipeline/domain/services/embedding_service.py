"""Embedding service for generating vector embeddings.

Responsible for coordinating the embedding of text chunks.
Single Responsibility: Generate embeddings for chunks using a provider.
"""

from collections.abc import Callable
from datetime import UTC, datetime

from lovdata_pipeline.domain.embedding_provider import EmbeddingProvider
from lovdata_pipeline.domain.models import ChunkMetadata, EnrichedChunk


class EmbeddingService:
    """Service for embedding text chunks.

    Single Responsibility: Generate embeddings using a provider,
    decoupled from progress tracking and specific embedding implementations.
    """

    def __init__(self, provider: EmbeddingProvider, batch_size: int = 100):
        """Initialize embedding service.

        Args:
            provider: Embedding provider implementation
            batch_size: Number of chunks to embed in each batch
        """
        self._provider = provider
        self._batch_size = batch_size

    def embed_chunks(
        self,
        chunks: list[ChunkMetadata],
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> list[EnrichedChunk]:
        """Embed chunks in batches.

        Args:
            chunks: List of chunks to embed
            progress_callback: Optional callback(current, total) for progress tracking

        Returns:
            List of enriched chunks with embeddings

        Raises:
            Exception: If embedding fails
        """
        all_enriched = []
        total_chunks = len(chunks)
        model_name = self._provider.get_model_name()

        for i in range(0, len(chunks), self._batch_size):
            batch = chunks[i : i + self._batch_size]
            texts = [c.text for c in batch]

            # Get embeddings from provider
            embeddings = self._provider.embed_batch(texts)

            # Create enriched chunks
            embedded_at = datetime.now(UTC).isoformat()
            for chunk, embedding in zip(batch, embeddings, strict=True):
                enriched = EnrichedChunk(
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    dataset_name=chunk.dataset_name,
                    content=chunk.content,
                    token_count=chunk.token_count,
                    section_heading=chunk.section_heading,
                    absolute_address=chunk.absolute_address,
                    split_reason=chunk.split_reason,
                    parent_chunk_id=chunk.parent_chunk_id,
                    embedding=embedding,
                    embedding_model=model_name,
                    embedded_at=embedded_at,
                )
                all_enriched.append(enriched)

            # Call progress callback if provided
            if progress_callback:
                progress_callback(len(all_enriched), total_chunks)

        return all_enriched
