"""Abstract base class for vector database clients.

This module defines the interface that all vector database implementations
must follow, making it easy to swap out ChromaDB for other solutions like
Pinecone, Weaviate, Qdrant, etc.
"""

from abc import ABC, abstractmethod
from typing import Any

from lovdata_pipeline.domain.models import EnrichedChunk


class VectorDBClient(ABC):
    """Abstract base class for vector database operations.

    All vector database clients must implement these methods to ensure
    consistent behavior across different backends.

    Implementations should handle:
    - Collection/index management
    - Vector upserts with metadata
    - Vector deletions
    - Metadata-based queries
    - Collection information retrieval
    """

    @abstractmethod
    def upsert(self, chunks: list[EnrichedChunk]) -> None:
        """Insert or update vectors in the database.

        Args:
            chunks: List of enriched chunks with embeddings and metadata

        Raises:
            Exception: If upsert operation fails
        """
        pass

    @abstractmethod
    def delete(self, ids: list[str]) -> None:
        """Delete vectors by ID.

        Args:
            ids: List of vector IDs to delete

        Raises:
            Exception: If delete operation fails
        """
        pass

    @abstractmethod
    def delete_by_file_path(self, file_path: str) -> int:
        """Delete all vectors for a specific file path.

        Args:
            file_path: File path to delete vectors for

        Returns:
            Number of vectors deleted

        Raises:
            Exception: If delete operation fails
        """
        pass

    @abstractmethod
    def get_vector_ids(self, where: dict[str, Any] | None = None) -> list[str]:
        """Get vector IDs matching metadata filters.

        Args:
            where: Optional metadata filter dict (e.g., {"document_id": "doc1"})

        Returns:
            List of vector IDs matching the filter

        Raises:
            Exception: If query operation fails
        """
        pass

    @abstractmethod
    def query(
        self,
        query_embeddings: list[list[float]],
        n_results: int = 10,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Query vectors by similarity.

        Args:
            query_embeddings: Query vectors
            n_results: Number of results to return
            where: Optional metadata filter

        Returns:
            Query results with ids, distances, metadatas, etc.

        Raises:
            Exception: If query operation fails
        """
        pass

    @abstractmethod
    def get_collection_info(self) -> dict[str, Any]:
        """Get information about the collection/index.

        Returns:
            Dict with collection info (name, count, metadata, etc.)

        Raises:
            Exception: If operation fails
        """
        pass

    @abstractmethod
    def delete_collection(self) -> None:
        """Delete the entire collection/index.

        Warning: This is a destructive operation.

        Raises:
            Exception: If delete operation fails
        """
        pass
