"""Vector store repository abstraction.

Decouples vector storage operations from specific implementations (ChromaDB, Pinecone, etc.)
"""

from typing import Protocol

from lovdata_pipeline.domain.models import EnrichedChunk


class VectorStoreRepository(Protocol):
    """Protocol for vector store operations.

    This allows swapping between different vector database implementations
    without changing business logic.
    """

    def upsert_chunks(self, chunks: list[EnrichedChunk]) -> None:
        """Store or update chunks in the vector database.

        Args:
            chunks: List of enriched chunks with embeddings to store

        Raises:
            Exception: If storage operation fails
        """
        ...

    def delete_by_document_id(self, vector_ids: list[str]) -> None:
        """Delete vectors by their IDs.

        Args:
            vector_ids: List of vector IDs to delete

        Raises:
            Exception: If deletion fails
        """
        ...

    def count(self) -> int:
        """Get total count of vectors in the store.

        Returns:
            Number of vectors stored

        Raises:
            Exception: If count operation fails
        """
        ...
