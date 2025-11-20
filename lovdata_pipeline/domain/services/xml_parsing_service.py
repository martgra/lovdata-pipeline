"""XML parsing service for legal documents.

DEPRECATED: This module is deprecated. The new LovdataChunker from
lovdata_pipeline.domain.parsers.lovdata_chunker handles XML parsing
and chunking in a single pass, with better structure preservation.

Responsible for parsing XML files and extracting legal articles.
Single Responsibility: XML parsing and article extraction.
"""

from pathlib import Path

from lxml import etree as ET


class ParsedArticle:
    """Represents a parsed legal article.

    This is a lightweight DTO (Data Transfer Object) that separates
    parsing concerns from domain models.
    """

    def __init__(
        self,
        article_id: str,
        content: str,
        heading: str,
        address: str,
    ):
        """Initialize the parsed article result.

        Args:
            article_id: Unique identifier for the article
            content: Full text content of the article
            heading: Article heading/title
            address: Legal address/reference for the article
        """
        self.article_id = article_id
        self.content = content
        self.heading = heading
        self.address = address


class XMLParsingService:
    """Service for parsing legal XML documents.

    Single Responsibility: Extract legal articles from XML files.
    """

    def parse_file(self, xml_path: Path) -> list[ParsedArticle]:
        """Parse XML file and extract legal articles.

        Uses a three-tier fallback strategy:
        1. Standard laws: Extract legalArticle elements (most modern laws)
        2. Change laws: Extract legalP elements within section elements
        3. Simple laws: Extract legalP elements directly under main (very old laws)

        Args:
            xml_path: Path to XML file to parse

        Returns:
            List of parsed articles

        Raises:
            Exception: If XML parsing fails
        """
        tree = ET.parse(str(xml_path))
        root = tree.getroot()
        articles = []

        # 1. Try standard legalArticle elements
        for elem in root.xpath('//article[@class="legalArticle"]'):
            article = self._extract_article(elem)
            if article:
                articles.append(article)

        # 2. If no legalArticle found, try change law structure (legalP in sections)
        if not articles:
            articles = self._extract_change_law_articles(root)

        # 3. If still no articles, try simple law structure (legalP directly under main)
        if not articles:
            articles = self._extract_simple_law_articles(root)

        return articles

    def _extract_article(self, elem) -> ParsedArticle | None:
        """Extract article data from XML element.

        Args:
            elem: lxml element representing an article

        Returns:
            ParsedArticle if content is found, None otherwise
        """
        article_id = elem.get("id") or elem.get("data-name", "unknown")
        address = elem.get("data-lovdata-URL", "")

        # Get heading from h2/h3/h4 tags
        heading = self._extract_heading(elem)

        # Get all text content
        content = "".join(elem.itertext()).strip()

        if not content:
            return None

        return ParsedArticle(
            article_id=article_id,
            content=content,
            heading=heading,
            address=address,
        )

    def _extract_heading(self, elem) -> str:
        """Extract heading from article element.

        Args:
            elem: lxml element containing article

        Returns:
            Heading text or empty string if not found
        """
        for h_tag in ["h2", "h3", "h4"]:
            h = elem.find(f'.//{h_tag}[@class="legalArticleHeader"]')
            if h is not None and h.text:
                return h.text.strip()
        return ""

    def _extract_change_law_articles(self, root) -> list[ParsedArticle]:
        """Extract articles from change laws (endringslover).

        Change laws have legalP elements directly under section elements,
        not wrapped in legalArticle elements.

        Args:
            root: The root XML element

        Returns:
            List of ParsedArticle objects extracted from legalP elements
        """
        articles = []

        for section_elem in root.xpath('//section[@class="section"]'):
            # Get section heading
            section_heading_elem = section_elem.find(".//h2")
            section_heading = (
                "".join(section_heading_elem.itertext()).strip()
                if section_heading_elem is not None
                else ""
            )

            # Get section URL
            section_url = section_elem.get("data-lovdata-URL", "")

            # Extract legalP elements directly under this section
            for legal_p_elem in section_elem.xpath('.//article[@class="legalP"]'):
                legal_p_id = legal_p_elem.get("id", "")
                article_id = legal_p_id if legal_p_id else f"{section_elem.get('id', 'unknown')}-p"

                content = "".join(legal_p_elem.itertext()).strip()

                if content:
                    articles.append(
                        ParsedArticle(
                            article_id=article_id,
                            content=content,
                            heading=section_heading,
                            address=section_url,
                        )
                    )

        return articles

    def _extract_simple_law_articles(self, root) -> list[ParsedArticle]:
        """Extract articles from very simple/old laws.

        Some very old laws have legalP elements directly under main
        without any section or legalArticle wrapper.

        Args:
            root: The root XML element

        Returns:
            List of ParsedArticle objects extracted from direct legalP elements
        """
        articles = []

        main_elem = root.find('.//main[@class="documentBody"]')
        if main_elem is None:
            return articles

        # Get document title from h1
        doc_title_elem = main_elem.find(".//h1")
        doc_title = "".join(doc_title_elem.itertext()).strip() if doc_title_elem is not None else ""

        # Get document URL
        doc_url = main_elem.get("data-lovdata-URL", "")

        # Extract legalP elements directly under main (not nested in sections)
        for idx, legal_p_elem in enumerate(main_elem.xpath('./article[@class="legalP"]'), start=1):
            legal_p_id = legal_p_elem.get("id", f"ledd-{idx}")
            content = "".join(legal_p_elem.itertext()).strip()

            if content:
                articles.append(
                    ParsedArticle(
                        article_id=legal_p_id,
                        content=content,
                        heading=doc_title,
                        address=doc_url,
                    )
                )

        return articles
