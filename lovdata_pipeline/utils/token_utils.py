"""Token estimation utilities for text processing.

This module provides shared utilities for estimating token counts
across the pipeline, ensuring consistency in batching and splitting logic.
"""

from __future__ import annotations


def estimate_tokens(text: str) -> int:
    """Estimate token count for text using character-based approximation.

    This is a simple heuristic (1 token ≈ 4 characters) that works well
    for Norwegian text. For exact counts, use tiktoken library.

    Args:
        text: Text to estimate tokens for

    Returns:
        Estimated token count
    """
    return len(text) // 4


def estimate_tokens_batch(texts: list[str]) -> list[int]:
    """Estimate tokens for a batch of texts.

    Args:
        texts: List of text strings

    Returns:
        List of token estimates corresponding to each text
    """
    return [estimate_tokens(text) for text in texts]


def total_tokens(texts: list[str]) -> int:
    """Calculate total tokens across multiple texts.

    Args:
        texts: List of text strings

    Returns:
        Sum of estimated tokens
    """
    return sum(estimate_tokens(text) for text in texts)
