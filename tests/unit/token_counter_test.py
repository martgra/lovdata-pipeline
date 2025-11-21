"""Unit tests for token counter.

Tests only critical token counting functionality. TokenCounter is a thin wrapper around tiktoken.
"""

from lovdata_pipeline.domain.splitters.token_counter import TokenCounter


def test_count_tokens():
    """Test token counting works for Norwegian legal text."""
    counter = TokenCounter()

    # Norwegian legal text with special characters
    text = "Lov av 1. januar 2024 § 1-1 første ledd med æøå."
    count = counter.count_tokens(text)

    assert count > 0
    assert isinstance(count, int)


def test_split_by_tokens():
    """Test splitting text by token count."""
    counter = TokenCounter()

    # Long text that needs splitting
    text = " ".join(["word"] * 1000)
    max_tokens = 100

    chunks = counter.split_by_tokens(text, max_tokens)

    assert len(chunks) > 1
    # Each chunk should be within limit
    for chunk in chunks:
        token_count = counter.count_tokens(chunk)
        assert token_count <= max_tokens + 5  # Small tolerance for boundary cases
