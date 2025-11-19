"""Unit tests for token counter."""

import pytest

from lovdata_pipeline.domain.splitters.token_counter import TokenCounter


def test_token_counter_initialization():
    """Test TokenCounter initializes correctly."""
    counter = TokenCounter()
    assert counter.encoding_name == "cl100k_base"


def test_count_tokens():
    """Test token counting."""
    counter = TokenCounter()

    # Simple English text
    text = "Hello world"
    count = counter.count_tokens(text)
    assert count > 0
    assert isinstance(count, int)

    # Norwegian text
    norwegian_text = "Dette er en norsk test med æøå."
    count = counter.count_tokens(norwegian_text)
    assert count > 0


def test_count_tokens_empty():
    """Test token counting with empty string."""
    counter = TokenCounter()
    assert counter.count_tokens("") == 0


def test_encode_decode():
    """Test encode and decode are inverse operations."""
    counter = TokenCounter()
    text = "This is a test with special characters: æøå!"

    # Encode then decode should give back original
    tokens = counter.encode(text)
    decoded = counter.decode(tokens)

    assert isinstance(tokens, list)
    assert len(tokens) > 0
    assert decoded == text


def test_split_by_tokens():
    """Test splitting text by token count."""
    counter = TokenCounter()

    # Long text that needs splitting
    text = " ".join(["word"] * 1000)  # Create a long text
    max_tokens = 100

    chunks = counter.split_by_tokens(text, max_tokens)

    assert len(chunks) > 1
    # Each chunk should be within limit (or very close)
    for chunk in chunks:
        token_count = counter.count_tokens(chunk)
        # Last chunk might be smaller
        assert token_count <= max_tokens + 5  # Small tolerance


def test_split_by_tokens_short_text():
    """Test splitting text that doesn't need splitting."""
    counter = TokenCounter()
    text = "Short text"
    max_tokens = 1000

    chunks = counter.split_by_tokens(text, max_tokens)

    assert len(chunks) == 1
    assert chunks[0] == text


def test_token_counter_with_different_encodings():
    """Test TokenCounter with different encoding."""
    counter = TokenCounter(encoding_name="cl100k_base")
    text = "Test text"

    count1 = counter.count_tokens(text)
    assert count1 > 0


def test_count_tokens_unicode():
    """Test token counting with Unicode characters."""
    counter = TokenCounter()

    # Legal Norwegian text with special characters
    text = "Lov av 1. januar 2024 § 1-1 første ledd."
    count = counter.count_tokens(text)

    assert count > 0
    assert isinstance(count, int)
