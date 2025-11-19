"""Token counting utilities using tiktoken.

This module provides a wrapper around tiktoken for counting tokens
in Norwegian legal text using the cl100k_base encoding (GPT-4/GPT-3.5).
"""

import tiktoken


class TokenCounter:
    """Count tokens in text using tiktoken.

    Uses the cl100k_base encoding which is used by GPT-4 and GPT-3.5-turbo.
    """

    def __init__(self, encoding_name: str = "cl100k_base") -> None:
        """Initialize the token counter.

        Args:
            encoding_name: Name of the tiktoken encoding to use
        """
        self.encoding = tiktoken.get_encoding(encoding_name)
        self.encoding_name = encoding_name

    def count_tokens(self, text: str) -> int:
        """Count the number of tokens in the given text.

        Args:
            text: Text to count tokens for

        Returns:
            Number of tokens
        """
        return len(self.encoding.encode(text))

    def encode(self, text: str) -> list[int]:
        """Encode text to token IDs.

        Args:
            text: Text to encode

        Returns:
            List of token IDs
        """
        return self.encoding.encode(text)

    def decode(self, token_ids: list[int]) -> str:
        """Decode token IDs back to text.

        Args:
            token_ids: List of token IDs

        Returns:
            Decoded text
        """
        return self.encoding.decode(token_ids)

    def split_by_tokens(self, text: str, max_tokens: int) -> list[str]:
        """Split text into chunks by token count.

        This is a hard split that doesn't respect any boundaries.
        Use as last resort when other splitting methods fail.

        Args:
            text: Text to split
            max_tokens: Maximum tokens per chunk

        Returns:
            List of text chunks
        """
        tokens = self.encode(text)
        chunks = []

        for i in range(0, len(tokens), max_tokens):
            chunk_tokens = tokens[i : i + max_tokens]
            chunk_text = self.decode(chunk_tokens)
            chunks.append(chunk_text)

        return chunks
