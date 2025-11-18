"""Dagster resource for ChromaDB vector database.

This module provides a Dagster resource for managing ChromaDB collections
and operations for legal document embeddings.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dagster import ConfigurableResource

if TYPE_CHECKING:
    import chromadb
    from chromadb.api.models.Collection import Collection


class ChromaDBResource(ConfigurableResource):
    """Dagster resource for ChromaDB vector database.

    This resource manages connections to ChromaDB and provides methods
    for creating collections and performing vector operations.

    This resource is decoupled from specific embedding providers - assets
    are responsible for providing the appropriate embedding function.

    Attributes:
        persist_directory: Directory path for ChromaDB persistence
        collection_name: Name of the collection for legal documents
        distance_metric: Distance metric for similarity search
    """

    persist_directory: str = "./data/chromadb"
    collection_name: str = "lovdata_legal"
    distance_metric: str = "cosine"

    def get_client(self) -> chromadb.PersistentClient:
        """Get ChromaDB persistent client.

        Returns:
            ChromaDB PersistentClient instance
        """
        import chromadb

        return chromadb.PersistentClient(path=self.persist_directory)

    def get_collection(self) -> Collection:
        """Get existing ChromaDB collection (read-only operations).

        Use this method for read, query, and delete operations that don't
        require an embedding function.

        Returns:
            ChromaDB Collection instance

        Raises:
            ValueError: If collection doesn't exist
        """
        client = self.get_client()

        try:
            return client.get_collection(name=self.collection_name)
        except Exception as e:
            raise ValueError(
                f"Collection '{self.collection_name}' does not exist. "
                "Use get_or_create_collection() with an embedding function first."
            ) from e

    def get_or_create_collection(self, embedding_function: Any) -> Collection:
        """Get or create ChromaDB collection with embedding function.

        Use this method when writing embeddings or when the embedding function
        is needed for collection creation.

        Args:
            embedding_function: Embedding function (e.g., OpenAIEmbeddingFunction).
                              Required - caller must provide the appropriate function.

        Returns:
            ChromaDB Collection instance

        Example:
            >>> from chromadb.utils import embedding_functions
            >>> import os
            >>>
            >>> # Asset provides the embedding function
            >>> emb_fn = embedding_functions.OpenAIEmbeddingFunction(
            ...     api_key=os.getenv("OPENAI_API_KEY"),
            ...     model_name="text-embedding-3-large"
            ... )
            >>> collection = chromadb.get_or_create_collection(emb_fn)
        """
        client = self.get_client()

        return client.get_or_create_collection(
            name=self.collection_name,
            metadata={
                "hnsw:space": self.distance_metric,
                "hnsw:batch_size": 100,
                "hnsw:sync_threshold": 1000,
                "description": "Norwegian legal documents from Lovdata",
                "document_type": "legal",
                "source": "lovdata",
            },
            embedding_function=embedding_function,
        )

    def delete_by_document_id(self, document_id: str) -> int:
        """Delete all chunks for a specific document.

        Args:
            document_id: Document ID to delete chunks for

        Returns:
            Number of chunks deleted
        """
        collection = self.get_collection()

        # Get chunks matching document ID
        chunks = collection.get(where={"document_id": {"$eq": document_id}}, include=[])

        if chunks["ids"]:
            collection.delete(ids=chunks["ids"])
            return len(chunks["ids"])

        return 0
