"""Dagster resource for OpenAI embeddings.

This resource wraps the OpenAI client and provides embedding functionality
for Dagster assets.
"""

from pathlib import Path

from dagster import ConfigurableResource
from openai import OpenAI

from lovdata_pipeline.domain.models import FileMetadata
from lovdata_pipeline.infrastructure.embedded_file_client import EmbeddedFileClient


class EmbeddingResource(ConfigurableResource):
    """Dagster resource for embedding operations.

    This resource provides methods to:
    - Track which files have been embedded
    - Embed text using OpenAI's API
    - Manage embedded file state

    Configuration:
        model_name: OpenAI embedding model (default: 'text-embedding-3-large')
        api_key: OpenAI API key (from environment)
        embedded_state_file: Path to embedded_files.json
        lovlig_state_file: Path to lovlig's state.json
        batch_size: Number of texts to embed in one API call
    """

    model_name: str = "text-embedding-3-large"
    api_key: str
    embedded_state_file: str = "./data/embedded_files.json"
    lovlig_state_file: str = "./data/state.json"
    batch_size: int = 100

    def _get_openai_client(self) -> OpenAI:
        """Create OpenAI client with current configuration.

        Returns:
            Configured OpenAI client
        """
        return OpenAI(api_key=self.api_key)

    def _get_embedded_client(self) -> EmbeddedFileClient:
        """Create embedded file tracking client.

        Returns:
            Configured EmbeddedFileClient
        """
        return EmbeddedFileClient(
            embedded_state_file=Path(self.embedded_state_file),
            lovlig_state_file=Path(self.lovlig_state_file),
        )

    def get_files_needing_embedding(
        self, changed_file_paths: list[str], force_reembed: bool = False
    ) -> list[FileMetadata]:
        """Get files that need embedding.

        Returns files where:
        - File hash changed since last embedding OR
        - File never been embedded OR
        - force_reembed=True

        Args:
            changed_file_paths: List of file paths that have changed
            force_reembed: If True, return all files regardless of embedded state

        Returns:
            List of FileMetadata objects for files needing embedding
        """
        client = self._get_embedded_client()
        return client.get_files_needing_embedding(changed_file_paths, force_reembed)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts using OpenAI API.

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors (each is a list of floats)

        Raises:
            Exception: If API call fails
        """
        if not texts:
            return []

        client = self._get_openai_client()

        # Call OpenAI embeddings API
        response = client.embeddings.create(input=texts, model=self.model_name)

        # Extract embeddings in order
        embeddings = [item.embedding for item in response.data]

        return embeddings

    def mark_file_embedded(
        self,
        dataset_name: str,
        file_path: str,
        file_hash: str,
        chunk_count: int,
        embedded_at: str | None = None,
    ) -> None:
        """Mark a file as successfully embedded.

        Updates embedded_files.json with embedding metadata.

        Args:
            dataset_name: Dataset name (e.g., 'gjeldende-lover.tar.bz2')
            file_path: Relative file path within dataset
            file_hash: SHA256 hash of file contents
            chunk_count: Number of chunks embedded
            embedded_at: Optional ISO timestamp (defaults to now)
        """
        client = self._get_embedded_client()
        client.mark_file_embedded(
            dataset_name=dataset_name,
            file_path=file_path,
            file_hash=file_hash,
            chunk_count=chunk_count,
            model_name=self.model_name,
            embedded_at=embedded_at,
        )

    def clean_removed_files(self) -> int:
        """Remove entries for files that no longer exist.

        Returns:
            Number of entries removed
        """
        client = self._get_embedded_client()
        return client.clean_removed_files()
