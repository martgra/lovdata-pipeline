"""XML parsing service for legal documents.

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

        for elem in root.xpath('//article[@class="legalArticle"]'):
            article = self._extract_article(elem)
            if article:
                articles.append(article)

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
