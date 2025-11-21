"""Metadata enrichment service for legal document chunks.

Provides a plugin-style architecture for extracting and enriching chunk metadata.
Each enrichment function can be easily added, removed, or modified.
"""

import logging
import re
from typing import Any, Protocol

from lxml import etree

logger = logging.getLogger(__name__)


# Helper functions for clean XML extraction
def _get_xml_text(root: etree._Element, xpath: str) -> str | None:
    """Extract text from XML element using XPath."""
    elem = root.find(xpath)
    return elem.text.strip() if elem is not None and elem.text else None


def _get_xml_attr(element: etree._Element | None, attr: str) -> str | None:
    """Get attribute from XML element."""
    return element.get(attr) if element is not None else None


class ChunkEnricher(Protocol):
    """Protocol for chunk enrichment functions.

    Each enricher takes the raw chunk data and XML root, and returns
    a dictionary of metadata fields to add/update.
    """

    def __call__(
        self,
        chunk_data: dict[str, Any],
        xml_root: etree._Element,
        chunk_element: etree._Element | None = None,
    ) -> dict[str, Any]:
        """Enrich chunk metadata.

        Args:
            chunk_data: Current chunk data with at least 'chunk_id' and 'text'
            xml_root: Root element of the source XML document
            chunk_element: The specific XML element for this chunk (if available)

        Returns:
            Dictionary of metadata fields to add/update
        """
        ...


class MetadataEnrichmentService:
    """Service for enriching chunk metadata using configurable enrichment functions.

    Uses a plugin-style architecture where enrichment functions can be easily
    added, removed, or reordered. Each function extracts specific metadata fields.

    Example:
        >>> service = MetadataEnrichmentService()
        >>> service.add_enricher(extract_document_title)
        >>> service.add_enricher(extract_references)
        >>> metadata = service.enrich(chunk_data, xml_root)
    """

    def __init__(self):
        """Initialize the enrichment service with default enrichers."""
        self._enrichers: list[tuple[str, ChunkEnricher]] = []

        # Register default enrichers
        self.add_enricher("document_info", extract_document_info)
        self.add_enricher("location_info", extract_location_info)
        self.add_enricher("hierarchy_info", extract_hierarchy_info)
        self.add_enricher("references", extract_references)
        self.add_enricher("section_context", extract_section_context)

    def add_enricher(self, name: str, enricher: ChunkEnricher) -> None:
        """Add an enrichment function.

        Args:
            name: Name of the enricher (for logging/debugging)
            enricher: Enrichment function following ChunkEnricher protocol
        """
        self._enrichers.append((name, enricher))
        logger.debug(f"Added enricher: {name}")

    def remove_enricher(self, name: str) -> bool:
        """Remove an enrichment function by name.

        Args:
            name: Name of the enricher to remove

        Returns:
            True if enricher was found and removed, False otherwise
        """
        original_count = len(self._enrichers)
        self._enrichers = [(n, e) for n, e in self._enrichers if n != name]
        removed = len(self._enrichers) < original_count
        if removed:
            logger.debug(f"Removed enricher: {name}")
        return removed

    def list_enrichers(self) -> list[str]:
        """Get list of registered enricher names.

        Returns:
            List of enricher names in execution order
        """
        return [name for name, _ in self._enrichers]

    def enrich(
        self,
        chunk_data: dict[str, Any],
        xml_root: etree._Element,
        chunk_element: etree._Element | None = None,
    ) -> dict[str, Any]:
        """Enrich chunk metadata using all registered enrichers.

        Args:
            chunk_data: Base chunk data (at minimum: chunk_id, text, token_count)
            xml_root: Root element of the source XML document
            chunk_element: The specific XML element for this chunk (if available)

        Returns:
            Enriched metadata dictionary with all extracted fields
        """
        enriched = dict(chunk_data)

        for name, enricher in self._enrichers:
            try:
                additional_metadata = enricher(enriched, xml_root, chunk_element)
                if additional_metadata:
                    enriched.update(additional_metadata)
            except Exception as e:
                logger.warning(f"Enricher '{name}' failed: {e}", exc_info=True)
                # Continue with other enrichers

        return enriched


# ============================================================================
# Default Enrichment Functions
# ============================================================================


def extract_document_info(
    chunk_data: dict[str, Any],
    xml_root: etree._Element,
    chunk_element: etree._Element | None = None,
) -> dict[str, Any]:
    """Extract document-level information."""
    metadata = {}

    if title := _get_xml_text(xml_root, './/dd[@class="title"]'):
        metadata["document_title"] = title

    if short_title := _get_xml_text(xml_root, './/dd[@class="titleShort"]'):
        metadata["document_short_title"] = short_title

    # Extract date from dokid (e.g., "NL/lov/1751-10-02")
    if (dokid := _get_xml_text(xml_root, './/dd[@class="dokid"]')) and (
        date_match := re.search(r"(\d{4}-\d{2}-\d{2})", dokid)
    ):
        metadata["document_date"] = date_match.group(1)

    if dept := _get_xml_text(xml_root, './/dd[@class="ministry"]//li'):
        metadata["department"] = dept

    return metadata


def extract_location_info(
    chunk_data: dict[str, Any],
    xml_root: etree._Element,
    chunk_element: etree._Element | None = None,
) -> dict[str, Any]:
    """Extract location/citation information."""
    metadata = {}

    if address := _get_xml_attr(chunk_element, "data-absoluteaddress"):
        metadata["absolute_address"] = address

    if url := _get_xml_attr(chunk_element, "data-lovdata-URL"):
        metadata["lovdata_url"] = url
        # Use URL as fallback for absolute_address
        if "absolute_address" not in metadata:
            metadata["absolute_address"] = url

    # Extract paragraph reference from chunk_id
    chunk_id = chunk_data.get("chunk_id", "")
    if para_match := re.search(r"(?:paragraf-|§\s*)(\d+[a-z]?)", chunk_id):
        metadata["paragraph_ref"] = f"§ {para_match.group(1)}"

    return metadata


def extract_hierarchy_info(
    chunk_data: dict[str, Any],
    xml_root: etree._Element,
    chunk_element: etree._Element | None = None,
) -> dict[str, Any]:
    """Extract hierarchical context information."""
    metadata = {}

    # Preserve existing hierarchy metadata
    for key in ("chapter_path", "parent_chunk_id"):
        if key in chunk_data:
            metadata[key] = chunk_data[key]

    # Calculate depth from chunk_id structure
    chunk_id = chunk_data.get("chunk_id", "")
    if depth := chunk_id.count("-"):
        metadata["depth_level"] = depth

    return metadata


def extract_references(
    chunk_data: dict[str, Any],
    xml_root: etree._Element,
    chunk_element: etree._Element | None = None,
) -> dict[str, Any]:
    """Extract cross-references to other laws and regulations.

    Extracts:
    - outgoing_refs: List of references to other laws (href values)
    - reference_count: Number of outgoing references

    Args:
        chunk_data: Current chunk data
        xml_root: Root element of XML document
        chunk_element: Specific chunk element

    Returns:
        Dictionary with reference info fields
    """
    metadata = {}

    # Extract from chunk text if we have the element
    if chunk_element is not None:
        refs = []
        for link in chunk_element.findall(".//a[@href]"):
            href = link.get("href")
            if href and href.startswith("lov/"):
                refs.append(href)

        if refs:
            metadata["outgoing_refs"] = refs
            metadata["reference_count"] = len(refs)
    else:
        # Fallback: extract from text using regex
        text = chunk_data.get("text", "")
        # Look for Lovdata reference patterns
        refs = re.findall(r'lov/\d{4}-\d{2}-\d{2}-\d+(?:/[^"\s]+)?', text)
        if refs:
            metadata["outgoing_refs"] = list(set(refs))  # Deduplicate
            metadata["reference_count"] = len(metadata["outgoing_refs"])

    return metadata


def extract_section_context(
    chunk_data: dict[str, Any],
    xml_root: etree._Element,
    chunk_element: etree._Element | None = None,
) -> dict[str, Any]:
    """Extract section/heading context information.

    Extracts:
    - section_heading: The heading/title of the section
    - section_number: Section number if available
    - is_amendment: Whether this is an amendment section

    Args:
        chunk_data: Current chunk data
        xml_root: Root element of XML document
        chunk_element: Specific chunk element

    Returns:
        Dictionary with section context fields
    """
    metadata = {}

    # Section heading (from existing metadata or parent section)
    if "section_heading" in chunk_data:
        metadata["section_heading"] = chunk_data["section_heading"]
    elif chunk_element is not None:
        # Try to find parent section heading
        parent_section = chunk_element.xpath("ancestor::section[@class='section']")
        if parent_section:
            heading = parent_section[0].find(".//h2")
            if heading is not None and heading.text:
                metadata["section_heading"] = heading.text.strip()

    # Check if this is an amendment/change section
    if chunk_element is not None:
        changes_elem = chunk_element.find(".//article[@class='changesToParent']")
        if changes_elem is not None:
            metadata["is_amendment"] = True

    return metadata
