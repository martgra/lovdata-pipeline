"""ChromaDB vector store implementation."""

from chromadb import Collection

from lovdata_pipeline.domain.models import EnrichedChunk


class ChromaVectorStoreRepository:
    """ChromaDB implementation of VectorStoreRepository.

    Wraps ChromaDB operations for vector storage and retrieval.
    """

    def __init__(self, collection: Collection):
        """Initialize ChromaDB vector store.

        Args:
            collection: ChromaDB collection instance
        """
        self._collection = collection

    def upsert_chunks(self, chunks: list[EnrichedChunk]) -> None:
        """Store or update chunks in ChromaDB.

        Args:
            chunks: List of enriched chunks with embeddings to store

        Raises:
            Exception: If ChromaDB upsert operation fails
        """
        if not chunks:
            return

        self._collection.upsert(
            ids=[c.chunk_id for c in chunks],
            embeddings=[c.embedding for c in chunks],
            metadatas=[c.metadata for c in chunks],
            documents=[c.text for c in chunks],
        )

    def delete_by_document_id(self, vector_ids: list[str]) -> None:
        """Delete vectors by their IDs from ChromaDB.

        Args:
            vector_ids: List of vector IDs to delete

        Raises:
            Exception: If ChromaDB deletion fails
        """
        if not vector_ids:
            return

        self._collection.delete(ids=vector_ids)

    def count(self) -> int:
        """Get total count of vectors in ChromaDB collection.

        Returns:
            Number of vectors stored

        Raises:
            Exception: If ChromaDB count operation fails
        """
        return self._collection.count()
