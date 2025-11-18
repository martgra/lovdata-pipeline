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

    Attributes:
        persist_directory: Directory path for ChromaDB persistence
        collection_name: Name of the collection for legal documents
        distance_metric: Distance metric for similarity search
        embedding_model: OpenAI model name for embeddings
    """

    persist_directory: str = "./data/chromadb"
    collection_name: str = "lovdata_legal"
    distance_metric: str = "cosine"
    embedding_model: str = "text-embedding-3-large"

    def get_client(self) -> chromadb.PersistentClient:
        """Get ChromaDB persistent client.

        Returns:
            ChromaDB PersistentClient instance
        """
        import chromadb

        return chromadb.PersistentClient(path=self.persist_directory)

    def get_or_create_collection(self, embedding_function: Any | None = None) -> Collection:
        """Get or create ChromaDB collection with configuration.

        Args:
            embedding_function: Optional custom embedding function.
                              If None, uses OpenAI embeddings.

        Returns:
            ChromaDB Collection instance
        """
        import os

        from chromadb.utils import embedding_functions

        client = self.get_client()

        if embedding_function is None:
            embedding_function = embedding_functions.OpenAIEmbeddingFunction(
                api_key=os.getenv("OPENAI_API_KEY", ""),
                model_name=self.embedding_model,
            )

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
        collection = self.get_or_create_collection()

        # Get chunks matching document ID
        chunks = collection.get(where={"document_id": {"$eq": document_id}}, include=[])

        if chunks["ids"]:
            collection.delete(ids=chunks["ids"])
            return len(chunks["ids"])

        return 0
