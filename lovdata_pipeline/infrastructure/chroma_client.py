"""ChromaDB client for vector storage.

Simple wrapper around ChromaDB with no abstract base class.
"""

from typing import Any

from lovdata_pipeline.domain.models import EnrichedChunk

try:
    import chromadb

    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False


class ChromaClient:
    """Client for interacting with ChromaDB vector database.

    This client handles:
    - Collection management
    - Vector upserts with metadata
    - Vector deletions by document ID
    - Querying vectors

    Example:
        >>> client = ChromaClient(collection_name="legal_docs")
        >>> chunks = [enriched_chunk1, enriched_chunk2]
        >>> client.upsert(chunks)
        >>> vector_ids = client.get_vector_ids(where={"document_id": "doc-1"})
        >>> client.delete(ids=vector_ids)
    """

    def __init__(
        self,
        mode: str = "persistent",
        host: str = "localhost",
        port: int = 8000,
        collection_name: str = "legal_docs",
        persist_directory: str | None = None,
    ):
        """Initialize ChromaDB client.

        Args:
            mode: Deployment mode - 'memory', 'persistent', or 'client'
                - 'memory': In-memory ephemeral storage (data lost on restart)
                - 'persistent': Local persistent storage (data saved to disk)
                - 'client': Connect to remote ChromaDB server
            host: ChromaDB server host (used in 'client' mode)
            port: ChromaDB server port (used in 'client' mode)
            collection_name: Name of the collection to use
            persist_directory: Local directory path (used in 'persistent' mode)

        Raises:
            ImportError: If chromadb package is not installed
            ValueError: If mode is invalid
        """
        if not CHROMADB_AVAILABLE:
            raise ImportError("chromadb package is not installed. Install it with: uv add chromadb")

        valid_modes = {"memory", "persistent", "client"}
        if mode not in valid_modes:
            raise ValueError(f"Invalid mode '{mode}'. Must be one of: {valid_modes}")

        self.mode = mode
        self.collection_name = collection_name
        self.persist_directory = persist_directory

        # Initialize client based on mode
        if mode == "memory":
            # In-memory ephemeral mode
            self.client = chromadb.EphemeralClient()
        elif mode == "persistent":
            # Local persistent mode
            path = persist_directory or "./chroma_data"
            self.client = chromadb.PersistentClient(path=path)
        else:  # mode == "client"
            # Client/server mode
            self.client = chromadb.HttpClient(host=host, port=port)

        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"description": "Legal document embeddings from Lovdata"},
        )

    def upsert(self, chunks: list[EnrichedChunk]) -> None:
        """Upsert vectors into the collection.

        This will insert new vectors or update existing ones with the same IDs.

        Args:
            chunks: List of enriched chunks with embeddings and metadata
        """
        if not chunks:
            return

        # Extract data from chunks
        ids = [chunk.chunk_id for chunk in chunks]
        embeddings = [chunk.embedding for chunk in chunks]
        metadatas = [chunk.metadata for chunk in chunks]
        documents = [chunk.text for chunk in chunks]

        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
            documents=documents,
        )

    def delete(self, ids: list[str]) -> None:
        """Delete vectors by ID.

        Args:
            ids: List of vector IDs to delete
        """
        if not ids:
            return

        self.collection.delete(ids=ids)

    def delete_by_metadata(self, where: dict[str, Any]) -> int:
        """Delete vectors matching metadata filter.

        Args:
            where: Metadata filter (e.g., {"document_id": "doc-123"})

        Returns:
            Number of vectors deleted
        """
        # First get the IDs matching the filter
        vector_ids = self.get_vector_ids(where=where)

        if vector_ids:
            self.delete(ids=vector_ids)

        return len(vector_ids)

    def delete_by_file_path(self, file_path: str) -> int:
        """Delete all vectors for a specific file path.

        Args:
            file_path: File path to delete vectors for

        Returns:
            Number of vectors deleted
        """
        return self.delete_by_metadata(where={"file_path": file_path})

    def get_vector_ids(self, where: dict[str, Any]) -> list[str]:
        """Get vector IDs matching a metadata filter.

        Args:
            where: Metadata filter (e.g., {"document_id": "doc-123"})

        Returns:
            List of matching vector IDs
        """
        try:
            result = self.collection.get(where=where, include=[])
            return result.get("ids", [])
        except Exception:
            # If collection is empty or filter matches nothing
            return []

    def query(
        self,
        query_embeddings: list[list[float]],
        n_results: int = 10,
        where: dict[str, Any] | None = None,
    ) -> dict:
        """Query for similar vectors.

        Args:
            query_embeddings: List of query embedding vectors
            n_results: Number of results to return per query
            where: Optional metadata filter

        Returns:
            Query results with ids, distances, metadatas, documents
        """
        return self.collection.query(
            query_embeddings=query_embeddings,
            n_results=n_results,
            where=where,
        )

    def count(self) -> int:
        """Get total number of vectors in collection.

        Returns:
            Count of vectors
        """
        return self.collection.count()

    def reset(self) -> None:
        """Delete all vectors from the collection.

        WARNING: This will remove all data from the collection.
        """
        self.client.delete_collection(name=self.collection_name)
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"description": "Legal document embeddings from Lovdata"},
        )

    def get_collection_info(self) -> dict[str, Any]:
        """Get information about the collection.

        Returns:
            Dict with collection name, count, and metadata
        """
        return {
            "name": self.collection_name,
            "count": self.count(),
            "metadata": self.collection.metadata,
        }

    def delete_collection(self) -> None:
        """Delete the entire collection.

        WARNING: This is a destructive operation that removes all data.
        """
        self.client.delete_collection(name=self.collection_name)
