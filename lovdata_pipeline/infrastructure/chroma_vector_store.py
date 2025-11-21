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

    def delete_by_document_id(self, doc_id: str) -> int:
        """Delete all vectors for a document using metadata filter.

        Args:
            doc_id: Document ID to delete all chunks for

        Returns:
            Number of vectors deleted

        Raises:
            Exception: If ChromaDB deletion fails
        """
        if not doc_id:
            return 0

        # Get all vector IDs for this document
        result = self._collection.get(
            where={"document_id": doc_id},
            include=[],  # Only need IDs
        )
        vector_ids = result.get("ids", [])

        if vector_ids:
            self._collection.delete(ids=vector_ids)

        return len(vector_ids)

    def count(self) -> int:
        """Get total count of vectors in ChromaDB collection.

        Returns:
            Number of vectors stored

        Raises:
            Exception: If ChromaDB count operation fails
        """
        return self._collection.count()

    def get_all_document_ids(self) -> set[str]:
        """Get all unique document IDs in the store.

        Returns:
            Set of document IDs that have chunks stored

        Raises:
            Exception: If ChromaDB operations fail
        """
        # Get all chunks with only metadata
        result = self._collection.get(
            include=["metadatas"],
        )
        doc_ids = {meta["document_id"] for meta in result["metadatas"] if "document_id" in meta}
        return doc_ids
