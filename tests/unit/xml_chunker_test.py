"""Unit tests for XML chunker."""

from pathlib import Path
from tempfile import NamedTemporaryFile

import lxml.etree as ET
import pytest

from lovdata_pipeline.domain.parsers.xml_chunker import LegalArticle, LovdataXMLChunker


@pytest.fixture
def sample_xml():
    """Create a sample XML file for testing."""
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html lang="no">
<head><title>Test Law</title></head>
<body>
    <main class="documentBody" id="dokument">
        <h1>Test Law Document</h1>
        <article class="legalArticle" data-lovdata-URL="NL/lov/2024-01-01/§1" id="paragraf-1">
            <h2 class="legalArticleHeader">
                <span class="legalArticleValue">§ 1</span>.
            </h2>
            <article class="legalP" id="paragraf-1-ledd-1">
                This is the first paragraph of the legal article.
            </article>
            <article class="legalP" id="paragraf-1-ledd-2">
                This is the second paragraph of the legal article.
            </article>
        </article>
        <article class="legalArticle" data-lovdata-URL="NL/lov/2024-01-01/§2" id="paragraf-2">
            <h2 class="legalArticleHeader">
                <span class="legalArticleValue">§ 2</span>.
            </h2>
            <article class="legalP" id="paragraf-2-ledd-1">
                Second article with one paragraph.
            </article>
        </article>
        <article class="changesToParent">
            This should be ignored (not a legalArticle).
        </article>
    </main>
</body>
</html>"""

    with NamedTemporaryFile(mode="w", suffix=".xml", delete=False, encoding="utf-8") as f:
        f.write(xml_content)
        temp_path = f.name

    yield temp_path

    # Cleanup
    Path(temp_path).unlink()


def test_lovdata_xml_chunker_initialization(sample_xml):
    """Test LovdataXMLChunker initialization."""
    chunker = LovdataXMLChunker(sample_xml)

    assert chunker.file_path == Path(sample_xml)
    assert chunker.document_id == Path(sample_xml).stem


def test_extract_articles(sample_xml):
    """Test extracting articles from XML."""
    chunker = LovdataXMLChunker(sample_xml)
    articles = chunker.extract_articles()

    assert len(articles) == 2
    assert all(isinstance(a, LegalArticle) for a in articles)


def test_extract_articles_details(sample_xml):
    """Test that extracted articles have correct details."""
    chunker = LovdataXMLChunker(sample_xml)
    articles = chunker.extract_articles()

    # First article
    article1 = articles[0]
    assert article1.article_id == "paragraf-1"
    assert article1.absolute_address == "NL/lov/2024-01-01/§1"
    assert "§ 1" in article1.section_heading
    assert len(article1.paragraphs) == 2
    assert "first paragraph" in article1.content
    assert "second paragraph" in article1.content

    # Second article
    article2 = articles[1]
    assert article2.article_id == "paragraf-2"
    assert article2.absolute_address == "NL/lov/2024-01-01/§2"
    assert len(article2.paragraphs) == 1
    assert "Second article" in article2.content


def test_extract_paragraphs(sample_xml):
    """Test paragraph extraction."""
    chunker = LovdataXMLChunker(sample_xml)
    articles = chunker.extract_articles()

    article = articles[0]
    assert len(article.paragraphs) == 2
    assert "first paragraph" in article.paragraphs[0]
    assert "second paragraph" in article.paragraphs[1]


def test_file_not_found():
    """Test handling of non-existent file."""
    chunker = LovdataXMLChunker("/nonexistent/file.xml")

    with pytest.raises(FileNotFoundError):
        chunker.extract_articles()


def test_malformed_xml():
    """Test handling of malformed XML."""
    with NamedTemporaryFile(mode="w", suffix=".xml", delete=False, encoding="utf-8") as f:
        f.write("This is not valid XML <unclosed>")
        temp_path = f.name

    try:
        chunker = LovdataXMLChunker(temp_path)
        with pytest.raises(ET.ParseError):
            chunker.extract_articles()
    finally:
        Path(temp_path).unlink()


def test_empty_articles_filtered():
    """Test that articles with only headers are still extracted."""
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html>
<body>
    <main class="documentBody">
        <article class="legalArticle" id="empty-article">
            <h2 class="legalArticleHeader">Empty</h2>
        </article>
        <article class="legalArticle" id="valid-article">
            <article class="legalP">Valid content</article>
        </article>
    </main>
</body>
</html>"""

    with NamedTemporaryFile(mode="w", suffix=".xml", delete=False, encoding="utf-8") as f:
        f.write(xml_content)
        temp_path = f.name

    try:
        chunker = LovdataXMLChunker(temp_path)
        articles = chunker.extract_articles()

        # Both articles should be returned (even with just header text)
        assert len(articles) == 2
        # First has only header text
        assert articles[0].article_id == "empty-article"
        assert "Empty" in articles[0].content
        # Second has paragraph content
        assert articles[1].article_id == "valid-article"
        assert "Valid content" in articles[1].content
    finally:
        Path(temp_path).unlink()


def test_article_without_paragraphs():
    """Test article without explicit legalP elements."""
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html>
<body>
    <main class="documentBody">
        <article class="legalArticle" id="test-article">
            <h2 class="legalArticleHeader">§ 1</h2>
            <p>This is plain text without legalP wrapper.</p>
        </article>
    </main>
</body>
</html>"""

    with NamedTemporaryFile(mode="w", suffix=".xml", delete=False, encoding="utf-8") as f:
        f.write(xml_content)
        temp_path = f.name

    try:
        chunker = LovdataXMLChunker(temp_path)
        articles = chunker.extract_articles()

        assert len(articles) == 1
        article = articles[0]
        assert len(article.paragraphs) == 0  # No legalP elements
        assert "plain text" in article.content  # But content is still extracted
    finally:
        Path(temp_path).unlink()
