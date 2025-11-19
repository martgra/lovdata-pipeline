"""OpenAI embedding provider implementation."""

from openai import OpenAI


class OpenAIEmbeddingProvider:
    """OpenAI implementation of EmbeddingProvider.

    Wraps the OpenAI API for generating text embeddings.
    """

    def __init__(self, client: OpenAI, model: str):
        """Initialize OpenAI embedding provider.

        Args:
            client: Configured OpenAI client instance
            model: Model identifier (e.g., 'text-embedding-3-small')
        """
        self._client = client
        self._model = model

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts using OpenAI API.

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors (one per input text)

        Raises:
            Exception: If OpenAI API call fails
        """
        response = self._client.embeddings.create(input=texts, model=self._model)
        return [item.embedding for item in response.data]

    def get_model_name(self) -> str:
        """Get the OpenAI model identifier.

        Returns:
            Model name string
        """
        return self._model
