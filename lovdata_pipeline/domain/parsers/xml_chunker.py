"""XML-aware chunker for Lovdata legal documents.

DEPRECATED: This module is deprecated. Use LovdataChunker from
lovdata_pipeline.domain.parsers.lovdata_chunker instead, which provides
improved chunking with overlapping chunks optimized for RAG.

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

        The extraction follows a three-tier fallback strategy:
        1. Standard laws: Extract legalArticle elements (most modern laws)
        2. Change laws: Extract legalP elements within section elements (endringslover)
        3. Simple laws: Extract legalP elements directly under main (very old laws)

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

        # Find all legalArticle elements (standard laws)
        for article_elem in root.xpath('//article[@class="legalArticle"]'):
            article = self._parse_article(article_elem)
            if article:
                articles.append(article)

        # If no legalArticle elements found, try extracting legalP elements
        # directly under sections (change laws/endringslover)
        if not articles:
            articles = self._extract_change_law_articles(root)

        # If still no articles, try extracting legalP elements directly
        # under main (very old/simple laws without section structure)
        if not articles:
            articles = self._extract_simple_law_articles(root)

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

    def _extract_change_law_articles(self, root: ET._Element) -> list[LegalArticle]:
        """Extract articles from change laws (endringslover).

        Change laws have legalP elements directly under section elements,
        not wrapped in legalArticle elements.

        Args:
            root: The root XML element

        Returns:
            List of LegalArticle objects extracted from legalP elements
        """
        articles = []

        # Find all sections with legalP children
        for section_elem in root.xpath('//section[@class="section"]'):
            # Get section heading
            section_heading_elem = section_elem.find(".//h2")
            section_heading = (
                self._get_text_recursive(section_heading_elem).strip()
                if section_heading_elem is not None
                else ""
            )

            # Get section URL for context
            section_url = section_elem.get("data-lovdata-URL", "")

            # Extract legalP elements directly under this section
            for legal_p_elem in section_elem.xpath('.//article[@class="legalP"]'):
                # Use the section ID + legalP ID as article ID
                legal_p_id = legal_p_elem.get("id", "")
                article_id = legal_p_id if legal_p_id else f"{section_elem.get('id', 'unknown')}-p"

                # Extract text content
                content = self._get_text_recursive(legal_p_elem).strip()

                if content:
                    article = LegalArticle(
                        article_id=article_id,
                        content=content,
                        paragraphs=[content],  # Single paragraph for legalP
                        section_heading=section_heading,
                        absolute_address=section_url,
                        document_id=self.document_id,
                    )
                    articles.append(article)

        return articles

    def _extract_simple_law_articles(self, root: ET._Element) -> list[LegalArticle]:
        """Extract articles from very simple/old laws.

        Some very old laws have legalP elements directly under main
        without any section or legalArticle wrapper.

        Args:
            root: The root XML element

        Returns:
            List of LegalArticle objects extracted from direct legalP elements
        """
        articles = []

        # Get the main document title for context
        main_elem = root.find('.//main[@class="documentBody"]')
        if main_elem is None:
            return articles

        # Get document title from h1
        doc_title_elem = main_elem.find(".//h1")
        doc_title = (
            self._get_text_recursive(doc_title_elem).strip() if doc_title_elem is not None else ""
        )

        # Get document URL for context
        doc_url = main_elem.get("data-lovdata-URL", "")

        # Extract legalP elements directly under main (not nested in sections)
        for idx, legal_p_elem in enumerate(main_elem.xpath('./article[@class="legalP"]'), start=1):
            # Use index-based ID since these simple laws often don't have IDs
            legal_p_id = legal_p_elem.get("id", f"ledd-{idx}")

            # Extract text content
            content = self._get_text_recursive(legal_p_elem).strip()

            if content:
                article = LegalArticle(
                    article_id=legal_p_id,
                    content=content,
                    paragraphs=[content],  # Single paragraph
                    section_heading=doc_title,  # Use document title as heading
                    absolute_address=doc_url,
                    document_id=self.document_id,
                )
                articles.append(article)

        return articles
