"""XML-aware chunker for Lovdata legal documents.

This module provides functionality to parse Lovdata XML documents and extract
legal articles with their structure preserved (paragraphs, headings, metadata).
"""

from dataclasses import dataclass
from pathlib import Path

import lxml.etree as ET


@dataclass
class LegalArticle:
    """Represents a single legal article extracted from XML.

    Attributes:
        article_id: Unique identifier for the article
        content: Full text content of the article
        paragraphs: List of paragraph texts if legalP elements exist
        section_heading: Title/heading of the section
        absolute_address: Lovdata absolute address (data-lovdata-URL attribute)
        document_id: ID of the source document
    """

    article_id: str
    content: str
    paragraphs: list[str]
    section_heading: str
    absolute_address: str
    document_id: str


class LovdataXMLChunker:
    """Parse Lovdata XML documents and extract legal articles.

    This chunker uses lxml to efficiently parse XML and extract legalArticle
    nodes along with their structured content (paragraphs, headings, metadata).
    """

    def __init__(self, file_path: str | Path) -> None:
        """Initialize the chunker with a file path.

        Args:
            file_path: Path to the XML file to parse
        """
        self.file_path = Path(file_path)
        self.document_id = self.file_path.stem  # e.g., "nl-19090323-000"

    def extract_articles(self) -> list[LegalArticle]:
        """Extract all legal articles from the XML document.

        Returns:
            List of LegalArticle objects

        Raises:
            FileNotFoundError: If the XML file does not exist
            ET.ParseError: If the XML is malformed
        """
        if not self.file_path.exists():
            raise FileNotFoundError(f"XML file not found: {self.file_path}")

        tree = ET.parse(str(self.file_path))
        root = tree.getroot()

        articles = []

        # Find all legalArticle elements
        for article_elem in root.xpath('//article[@class="legalArticle"]'):
            article = self._parse_article(article_elem)
            if article:
                articles.append(article)

        return articles

    def _parse_article(self, article_elem: ET._Element) -> LegalArticle | None:
        """Parse a single legalArticle element.

        Args:
            article_elem: The legalArticle XML element

        Returns:
            LegalArticle object or None if parsing fails
        """
        # Extract article ID from the 'id' or 'data-name' attribute
        article_id = article_elem.get("id", "")
        if not article_id:
            article_id = article_elem.get("data-name", "unknown")

        # Extract absolute address from data-lovdata-URL attribute
        absolute_address = article_elem.get("data-lovdata-URL", "")

        # Extract section heading from header element
        section_heading = self._extract_heading(article_elem)

        # Extract paragraphs (legalP elements)
        paragraphs = self._extract_paragraphs(article_elem)

        # Extract full text content
        content = self._extract_text(article_elem)

        if not content.strip():
            return None

        return LegalArticle(
            article_id=article_id,
            content=content,
            paragraphs=paragraphs,
            section_heading=section_heading,
            absolute_address=absolute_address,
            document_id=self.document_id,
        )

    def _extract_heading(self, article_elem: ET._Element) -> str:
        """Extract the section heading from the article.

        Args:
            article_elem: The legalArticle XML element

        Returns:
            Section heading text or empty string
        """
        # Try to find header element
        header = article_elem.find('.//h2[@class="legalArticleHeader"]')
        if header is None:
            header = article_elem.find('.//h3[@class="legalArticleHeader"]')
        if header is None:
            header = article_elem.find('.//h4[@class="legalArticleHeader"]')

        if header is not None:
            return self._get_text_recursive(header).strip()

        return ""

    def _extract_paragraphs(self, article_elem: ET._Element) -> list[str]:
        """Extract legalP paragraph texts from the article.

        Args:
            article_elem: The legalArticle XML element

        Returns:
            List of paragraph texts
        """
        paragraphs = []

        # Find all legalP elements (direct paragraphs)
        for para_elem in article_elem.xpath('.//article[@class="legalP"]'):
            text = self._get_text_recursive(para_elem).strip()
            if text:
                paragraphs.append(text)

        return paragraphs

    def _extract_text(self, elem: ET._Element) -> str:
        """Extract all text content from an element.

        Args:
            elem: The XML element

        Returns:
            All text content concatenated
        """
        return self._get_text_recursive(elem)

    def _get_text_recursive(self, elem: ET._Element) -> str:
        """Recursively extract text from element and all children.

        Args:
            elem: The XML element

        Returns:
            Text content with spacing preserved
        """
        # Use itertext() to get all text nodes
        texts = []
        for text in elem.itertext():
            if text.strip():
                texts.append(text.strip())

        return " ".join(texts)
