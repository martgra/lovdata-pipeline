"""Unit tests for recursive splitter."""

import pytest

from lovdata_pipeline.domain.parsers.xml_chunker import LegalArticle
from lovdata_pipeline.domain.splitters.recursive_splitter import XMLAwareRecursiveSplitter


@pytest.fixture
def splitter():
    """Create a splitter with reasonable token limit."""
    return XMLAwareRecursiveSplitter(max_tokens=100)


@pytest.fixture
def small_article():
    """Create a small article that fits in one chunk."""
    return LegalArticle(
        article_id="test-1",
        content="This is a short legal article that fits in one chunk.",
        paragraphs=["This is a short legal article that fits in one chunk."],
        section_heading="§ 1",
        absolute_address="NL/lov/2024/§1",
        document_id="test-doc",
    )


@pytest.fixture
def large_article_with_paragraphs():
    """Create a large article with multiple paragraphs."""
    paragraphs = [
        "This is the first paragraph with some legal text that describes rules. " * 10,
        "This is the second paragraph with more legal text and regulations. " * 10,
        "This is the third paragraph with additional provisions and details. " * 10,
    ]
    return LegalArticle(
        article_id="test-2",
        content=" ".join(paragraphs),
        paragraphs=paragraphs,
        section_heading="§ 2",
        absolute_address="NL/lov/2024/§2",
        document_id="test-doc",
    )


def test_split_article_no_split_needed(splitter, small_article):
    """Test that small articles don't get split."""
    chunks = splitter.split_article(small_article)

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.chunk_id == "test-doc_test-1"
    assert chunk.split_reason == "none"
    assert chunk.parent_chunk_id is None
    assert chunk.content == small_article.content
    assert chunk.section_heading == "§ 1"
    assert chunk.absolute_address == "NL/lov/2024/§1"


def test_split_article_by_paragraphs(splitter, large_article_with_paragraphs):
    """Test splitting by paragraphs."""
    chunks = splitter.split_article(large_article_with_paragraphs)

    assert len(chunks) > 1
    # Check that at least some chunks used paragraph splitting
    split_reasons = [c.split_reason for c in chunks]
    assert "paragraph" in split_reasons or "sentence" in split_reasons


def test_split_article_chunk_ids(splitter, large_article_with_paragraphs):
    """Test that chunk IDs are correct."""
    chunks = splitter.split_article(large_article_with_paragraphs)

    # First chunk should have base ID
    assert chunks[0].chunk_id == "test-doc_test-2"

    # Sub-chunks should have _sub_ suffix
    if len(chunks) > 1:
        for i, chunk in enumerate(chunks[1:], start=1):
            assert "_sub_" in chunk.chunk_id
            assert chunk.parent_chunk_id == "test-doc_test-2"


def test_split_article_token_counts(splitter, large_article_with_paragraphs):
    """Test that all chunks respect token limit."""
    chunks = splitter.split_article(large_article_with_paragraphs)

    for chunk in chunks:
        # Allow small tolerance for edge cases
        assert chunk.token_count <= splitter.max_tokens + 10


def test_split_by_sentences():
    """Test sentence-level splitting."""
    splitter = XMLAwareRecursiveSplitter(max_tokens=50)

    # Article with long text but no paragraphs
    long_text = (
        "This is the first sentence. This is the second sentence. "
        "This is the third sentence. This is the fourth sentence. " * 5
    )
    article = LegalArticle(
        article_id="test-3",
        content=long_text,
        paragraphs=[],  # No paragraphs
        section_heading="§ 3",
        absolute_address="NL/lov/2024/§3",
        document_id="test-doc",
    )

    chunks = splitter.split_article(article)

    assert len(chunks) > 1
    # Should use sentence splitting
    split_reasons = [c.split_reason for c in chunks]
    assert "sentence" in split_reasons


def test_split_by_tokens():
    """Test hard token splitting as last resort."""
    splitter = XMLAwareRecursiveSplitter(max_tokens=10)

    # Create text with very long "sentence" that can't be split at boundaries
    long_word = "a" * 1000
    article = LegalArticle(
        article_id="test-4",
        content=long_word,
        paragraphs=[],
        section_heading="§ 4",
        absolute_address="NL/lov/2024/§4",
        document_id="test-doc",
    )

    chunks = splitter.split_article(article)

    assert len(chunks) > 1
    # Should use token splitting
    split_reasons = [c.split_reason for c in chunks]
    assert "token" in split_reasons


def test_split_preserves_metadata():
    """Test that splitting preserves article metadata."""
    splitter = XMLAwareRecursiveSplitter(max_tokens=50)

    long_text = "Legal text that will be split. " * 20
    article = LegalArticle(
        article_id="test-5",
        content=long_text,
        paragraphs=[long_text],
        section_heading="§ 5 Important Section",
        absolute_address="NL/lov/2024/§5",
        document_id="test-doc-123",
    )

    chunks = splitter.split_article(article)

    for chunk in chunks:
        assert chunk.document_id == "test-doc-123"
        assert chunk.section_heading == "§ 5 Important Section"
        assert chunk.absolute_address == "NL/lov/2024/§5"


def test_empty_article():
    """Test handling of empty article."""
    splitter = XMLAwareRecursiveSplitter(max_tokens=100)

    article = LegalArticle(
        article_id="empty",
        content="",
        paragraphs=[],
        section_heading="",
        absolute_address="",
        document_id="test-doc",
    )

    chunks = splitter.split_article(article)

    assert len(chunks) == 1
    assert chunks[0].token_count == 0


def test_split_with_norwegian_text():
    """Test splitting with Norwegian legal text."""
    splitter = XMLAwareRecursiveSplitter(max_tokens=50)

    norwegian_text = (
        "Loven gjelder for alle. Den som overtrer loven kan straffes. "
        "Forskrifter fastsettes av departementet. Ikrafttredelse bestemmes av Kongen. " * 5
    )
    article = LegalArticle(
        article_id="nor-1",
        content=norwegian_text,
        paragraphs=[],
        section_heading="§ 1",
        absolute_address="LOV/2024/§1",
        document_id="nor-doc",
    )

    chunks = splitter.split_article(article)

    assert len(chunks) > 1
    # Verify Norwegian text is preserved
    combined = " ".join(c.content for c in chunks)
    assert "gjelder" in combined
    assert "departementet" in combined


def test_split_distribution():
    """Test that splitter uses optimal strategy."""
    splitter = XMLAwareRecursiveSplitter(max_tokens=100)

    # Article with well-structured paragraphs
    paragraphs = [f"Paragraph {i} with legal text. " * 10 for i in range(5)]
    article = LegalArticle(
        article_id="dist-1",
        content=" ".join(paragraphs),
        paragraphs=paragraphs,
        section_heading="§ 1",
        absolute_address="LOV/2024/§1",
        document_id="dist-doc",
    )

    chunks = splitter.split_article(article)

    # Should prefer paragraph splitting for well-structured content
    split_reasons = [c.split_reason for c in chunks]
    paragraph_count = split_reasons.count("paragraph")
    sentence_count = split_reasons.count("sentence")

    # More paragraph splits than sentence splits for structured content
    assert paragraph_count >= sentence_count
