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


def test_change_law_extraction():
    """Test extraction of change laws (endringslover) with legalP directly under sections."""
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html lang="no">
<head><title>Change Law</title></head>
<body>
    <main class="documentBody" data-lovdata-URL="NL/lov/2003-06-20-44">
        <h1>Lov om endringer</h1>
        <section class="section" data-name="kapI" id="kapittel-1" data-lovdata-URL="NL/lov/2003-06-20-44/KAPITTEL_1">
            <h2>I</h2>
            <article class="legalP" id="kapittel-1-ledd-1">
                Lov 14. juli 1950 nr. 10 om valutaregulering oppheves.
            </article>
        </section>
        <section class="section" data-name="kapII" id="kapittel-2" data-lovdata-URL="NL/lov/2003-06-20-44/KAPITTEL_2">
            <h2>II</h2>
            <article class="legalP" id="kapittel-2-ledd-1">
                Lov 25. juni 1965 nr. 2 om adgang til regulering oppheves.
            </article>
        </section>
        <section class="section" data-name="kapV" id="kapittel-3" data-lovdata-URL="NL/lov/2003-06-20-44/KAPITTEL_3">
            <h2>V</h2>
            <article class="legalP" id="kapittel-3-ledd-1">
                Loven trer i kraft fra den tid Kongen bestemmer.
            </article>
            <article class="legalP" id="kapittel-3-ledd-2">
                Kongen kan gi overgangsregler.
            </article>
        </section>
    </main>
</body>
</html>"""

    with NamedTemporaryFile(mode="w", suffix=".xml", delete=False, encoding="utf-8") as f:
        f.write(xml_content)
        temp_path = f.name

    try:
        chunker = LovdataXMLChunker(temp_path)
        articles = chunker.extract_articles()

        # Should extract 4 legalP elements (no legalArticle wrappers)
        assert len(articles) == 4

        # Check first article
        assert articles[0].article_id == "kapittel-1-ledd-1"
        assert articles[0].section_heading == "I"
        assert "valutaregulering oppheves" in articles[0].content
        assert articles[0].absolute_address == "NL/lov/2003-06-20-44/KAPITTEL_1"

        # Check second article
        assert articles[1].article_id == "kapittel-2-ledd-1"
        assert articles[1].section_heading == "II"
        assert "regulering oppheves" in articles[1].content

        # Check third and fourth articles (both under section V)
        assert articles[2].article_id == "kapittel-3-ledd-1"
        assert articles[2].section_heading == "V"
        assert "trer i kraft" in articles[2].content

        assert articles[3].article_id == "kapittel-3-ledd-2"
        assert articles[3].section_heading == "V"
        assert "overgangsregler" in articles[3].content

    finally:
        Path(temp_path).unlink()


def test_simple_law_extraction():
    """Test extraction of simple/old laws with legalP directly under main."""
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html lang="no">
<head><title>Old Simple Law</title></head>
<body>
    <main class="documentBody" data-lovdata-URL="NL/lov/1741-02-17" id="dokument">
        <h1>Forbud paa Vimpel-Føring</h1>
        <article class="legalP" id="ledd-1">
            Ingen Skipper, som fører noget i Kongens Riger og Lande hjemmehørende Skib.
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

        # Should extract 1 legalP element directly under main
        assert len(articles) == 1

        # Check article details
        assert articles[0].article_id == "ledd-1"
        assert articles[0].section_heading == "Forbud paa Vimpel-Føring"
        assert "Ingen Skipper" in articles[0].content
        assert articles[0].absolute_address == "NL/lov/1741-02-17"
        assert len(articles[0].paragraphs) == 1
        assert articles[0].paragraphs[0] == articles[0].content

    finally:
        Path(temp_path).unlink()
