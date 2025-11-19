"""Embedding provider abstraction.

Decouples the embedding logic from specific providers (OpenAI, Cohere, local models, etc.)
"""

from typing import Protocol


class EmbeddingProvider(Protocol):
    """Protocol for embedding providers.

    This allows swapping between different embedding implementations
    (OpenAI, Cohere, local models, etc.) without changing business logic.
    """

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts.

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors (one per input text)

        Raises:
            Exception: If embedding fails
        """
        ...

    def get_model_name(self) -> str:
        """Get the model identifier used for these embeddings.

        Returns:
            Model name/identifier string
        """
        ...
