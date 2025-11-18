"""Parse Lovdata XML documents and extract structured chunks.

This module provides XML parsing functionality for Norwegian legal documents
from Lovdata, using lxml for efficient parsing and XPath queries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from lovdata_pipeline.utils import estimate_tokens

if TYPE_CHECKING:
    import lxml.etree as ET
else:
    try:
        import lxml.etree as ET  # type: ignore
    except ImportError:
        ET = None  # type: ignore


@dataclass
class LegalChunk:
    """Structured representation of a legal document chunk.

    Attributes:
        chunk_id: Unique identifier for the chunk
        content: Full text content of the chunk
        metadata: Dictionary containing hierarchical and processing metadata
        is_split: Whether this chunk was split due to size limits
        split_index: Index of this sub-chunk if split (0-based)
        total_splits: Total number of sub-chunks if split
    """

    chunk_id: str
    content: str
    metadata: dict = field(default_factory=dict)
    is_split: bool = False
    split_index: int | None = None
    total_splits: int | None = None


class LovdataXMLParser:
    """Parse Lovdata XML documents and extract structured chunks.

    This parser handles the HTML5-compatible XML format used by Lovdata,
    preserving the hierarchical structure of Norwegian legal documents
    (Law -> Chapter -> § -> Paragraph).

    Features:
    - XML-aware chunking at legalArticle or legalP level
    - Token-aware splitting for oversized chunks
    - Preserves XML metadata and hierarchy
    - Splits at XML boundaries (legalP) before falling back to text splitting

    Attributes:
        chunk_level: XML class to use as chunk boundary
                    ('legalArticle' for §, 'legalP' for ledd)
        max_tokens: Maximum tokens per chunk (0 = unlimited)
        overlap_tokens: Token overlap between split chunks
    """

    def __init__(
        self, chunk_level: str = "legalArticle", max_tokens: int = 0, overlap_tokens: int = 0
    ):
        """Initialize parser with chunking configuration.

        Args:
            chunk_level: XML class to use as chunk boundary
                        ('legalArticle' for §, 'legalP' for ledd)
            max_tokens: Maximum tokens per chunk (0 = unlimited)
            overlap_tokens: Token overlap for split chunks

        Raises:
            ValueError: If chunk_level is not supported
        """
        if chunk_level not in ["legalArticle", "legalP"]:
            raise ValueError(
                f"Unsupported chunk_level: {chunk_level}. Must be 'legalArticle' or 'legalP'"
            )
        self.chunk_level = chunk_level
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens

    def parse_document(self, xml_path: str | Path) -> list[LegalChunk]:
        """Parse XML document and extract chunks with metadata.

        Args:
            xml_path: Path to XML file to parse

        Returns:
            List of LegalChunk objects with content and metadata

        Raises:
            ET.ParseError: If XML is malformed
            FileNotFoundError: If xml_path does not exist
        """
        xml_path = Path(xml_path)
        if not xml_path.exists():
            raise FileNotFoundError(f"XML file not found: {xml_path}")

        tree = ET.parse(str(xml_path))
        root = tree.getroot()

        # Extract document-level metadata
        doc_metadata = self._extract_document_metadata(root, xml_path)

        # Handle XML namespace if present
        nsmap = root.nsmap if hasattr(root, "nsmap") else {}
        # Remove None key if exists (default namespace)
        if None in nsmap:
            nsmap["ns"] = nsmap.pop(None)

        # Find all chunk elements using XPath
        chunks = []
        if self.chunk_level == "legalArticle":
            if nsmap:
                elements = root.xpath("//ns:article[@class='legalArticle']", namespaces=nsmap)
            else:
                elements = root.xpath("//article[@class='legalArticle']")
        else:  # legalP
            if nsmap:
                elements = root.xpath("//ns:article[@class='legalP']", namespaces=nsmap)
            else:
                elements = root.xpath("//article[@class='legalP']")

        for idx, element in enumerate(elements):
            chunk_list = self._process_element(element, idx, doc_metadata, nsmap)
            if chunk_list:
                chunks.extend(chunk_list)

        return chunks

    def _extract_document_metadata(self, root: ET.Element, xml_path: Path) -> dict:
        """Extract document-level metadata from XML root.

        Args:
            root: XML root element
            xml_path: Path to XML file for extracting document ID

        Returns:
            Dictionary with document metadata
        """
        # Extract title (usually in first h1)
        title_elem = root.find(".//h1")
        title = title_elem.text.strip() if title_elem is not None else "Unknown"

        # Extract document ID from filename (e.g., "LOV-1999-07-02-63.xml")
        doc_id = xml_path.stem

        # Determine document type from ID prefix
        doc_type_map = {
            "LOV": "law",
            "FOR": "regulation",
            "AVG": "decision",
            "SIR": "circular",
        }
        doc_type = doc_type_map.get(doc_id.split("-")[0], "unknown")

        return {
            "document_title": title,
            "document_id": doc_id,
            "document_type": doc_type,
            "source": "lovdata",
            "parsed_at": datetime.now(UTC).isoformat(),
        }

    def _process_element(
        self, element: ET.Element, idx: int, doc_metadata: dict, nsmap: dict
    ) -> list[LegalChunk]:
        """Process a single chunk element with token-aware splitting.

        Args:
            element: XML element to process
            idx: Index of element in document
            doc_metadata: Document-level metadata
            nsmap: XML namespace map

        Returns:
            List of LegalChunk objects (may be split if oversized)
        """
        # Extract hierarchical address
        absolute_address = element.get("data-absoluteaddress", "")
        element_id = element.get("id", f"chunk_{idx}")

        # Extract text content (including all nested elements)
        content = self._get_text_content(element)

        if not content.strip():
            return []

        # Count tokens
        token_count = estimate_tokens(content)

        # Extract parent context
        parent_context = self._extract_parent_context(element)

        # Check for special content types
        has_list_items = len(element.xpath(".//article[@class='listArticle']")) > 0
        has_footnotes = len(element.xpath(".//footer[@class='footnotes']")) > 0

        # Build base metadata
        metadata = {
            **doc_metadata,
            "chunk_index": idx,
            "absolute_address": absolute_address,
            "element_id": element_id,
            **parent_context,
            "chunk_length": len(content),
            "chunk_type": self.chunk_level,
            "has_list_items": has_list_items,
            "has_footnotes": has_footnotes,
            "xml_element_type": element.get("class", "unknown"),
            "extraction_method": "xml_structure",
        }

        # Generate base chunk ID
        base_chunk_id = f"{doc_metadata['document_id']}_{element_id}"

        # Check if splitting needed
        if self.max_tokens > 0 and token_count > self.max_tokens:
            # Split oversized element while preserving XML structure
            return self._split_oversized_element(
                element, content, base_chunk_id, metadata, token_count, nsmap
            )
        else:
            # Single chunk - no splitting needed
            metadata["token_count"] = token_count
            metadata["requires_splitting"] = False

            return [
                LegalChunk(
                    chunk_id=base_chunk_id,
                    content=content,
                    metadata=metadata,
                    is_split=False,
                )
            ]

    def _get_text_content(self, element: ET.Element) -> str:
        """Extract all text from element and children, preserving structure.

        Args:
            element: XML element to extract text from

        Returns:
            Concatenated text content with spacing preserved
        """
        texts = []

        # Get heading if present (h2, h3, etc.)
        for heading in element.xpath(".//h2 | .//h3"):
            if heading.text:
                texts.append(heading.text.strip())

        # Get all text content, excluding headings already captured
        for text_elem in element.xpath(".//text()"):
            # Skip if parent is a heading we already captured
            parent = text_elem.getparent()
            if parent is not None and parent.tag in ["h2", "h3"]:
                continue

            cleaned = text_elem.strip()
            if cleaned:
                texts.append(cleaned)

        return " ".join(texts)

    def _extract_parent_context(self, element: ET.Element) -> dict:
        """Extract parent section and chapter information.

        Args:
            element: Current element to find parents for

        Returns:
            Dictionary with chapter and section context
        """
        context = {}

        # Find parent section/chapter
        parent_section = element.xpath("ancestor::section[@class='section'][1]")
        if parent_section:
            section_heading = parent_section[0].find(".//h1")
            if section_heading is not None and section_heading.text:
                context["chapter_title"] = section_heading.text.strip()
                context["chapter_address"] = parent_section[0].get("data-absoluteaddress", "")

        # Find parent article (if chunk is legalP)
        if self.chunk_level == "legalP":
            parent_article = element.xpath("ancestor::article[@class='legalArticle'][1]")
            if parent_article:
                article_heading = parent_article[0].find(".//h2")
                if article_heading is not None and article_heading.text:
                    context["section_title"] = article_heading.text.strip()
                    context["section_address"] = parent_article[0].get("data-absoluteaddress", "")

        return context

    def _split_oversized_element(
        self,
        element: ET.Element,
        content: str,
        base_chunk_id: str,
        metadata: dict,
        total_tokens: int,
        nsmap: dict,
    ) -> list[LegalChunk]:
        """Split oversized element using XML structure, then text splitting.

        Strategy:
        1. If element is legalArticle: try splitting by legalP boundaries
        2. Otherwise: fall back to text-based splitting

        This preserves XML structure as much as possible!

        Args:
            element: XML element to split
            content: Text content of element
            base_chunk_id: Base ID for chunks
            metadata: Base metadata to preserve
            total_tokens: Total tokens in element
            nsmap: XML namespace map

        Returns:
            List of LegalChunk sub-chunks
        """
        # Strategy 1: Try XML-aware splitting at legalP boundaries
        if element.get("class") == "legalArticle":
            xml_chunks = self._split_by_legalp_boundaries(element, base_chunk_id, metadata, nsmap)
            if xml_chunks:
                return xml_chunks

        # Strategy 2: Fall back to text-based recursive splitting
        return self._split_by_text_boundaries(content, base_chunk_id, metadata, total_tokens)

    def _split_by_legalp_boundaries(
        self,
        element: ET.Element,
        base_chunk_id: str,
        metadata: dict,
        nsmap: dict,
    ) -> list[LegalChunk] | None:
        """Try to split legalArticle at legalP (paragraph) boundaries.

        This is the XML-aware splitting approach that respects structure!

        Args:
            element: legalArticle element to split
            base_chunk_id: Base chunk ID
            metadata: Base metadata
            nsmap: XML namespace map

        Returns:
            List of chunks if successful, None if legalP splitting won't work
        """
        # Find all legalP sub-elements
        if nsmap:
            sub_paragraphs = element.xpath(".//ns:article[@class='legalP']", namespaces=nsmap)
        else:
            sub_paragraphs = element.xpath(".//article[@class='legalP']")

        if not sub_paragraphs:
            return None  # No legalP elements to split by

        # Build chunks by batching legalP elements within token limits
        chunks = []
        current_batch_texts = []
        current_batch_ids = []
        current_tokens = 0

        # Get heading once (shared across all sub-chunks)
        heading_elem = element.find(".//h2")
        heading = (
            heading_elem.text.strip() if heading_elem is not None and heading_elem.text else None
        )

        for ledd_elem in sub_paragraphs:
            ledd_text = "".join(ledd_elem.itertext()).strip()
            ledd_tokens = estimate_tokens(ledd_text)
            ledd_id = ledd_elem.get("id", "unknown")

            # Check if single legalP exceeds limit (can't split further at XML level)
            if ledd_tokens > self.max_tokens:
                return None  # Fall back to text splitting

            # Check if adding this ledd would exceed limit
            if current_tokens + ledd_tokens > self.max_tokens and current_batch_texts:
                # Flush current batch as a chunk
                batch_content = "\n\n".join(current_batch_texts)
                if heading:
                    batch_content = f"{heading}\n\n{batch_content}"

                chunks.append(
                    {
                        "content": batch_content,
                        "tokens": current_tokens,
                        "ledd_ids": current_batch_ids.copy(),
                    }
                )

                # Start new batch
                current_batch_texts = [ledd_text]
                current_batch_ids = [ledd_id]
                current_tokens = ledd_tokens
            else:
                # Add to current batch
                current_batch_texts.append(ledd_text)
                current_batch_ids.append(ledd_id)
                current_tokens += ledd_tokens

        # Flush remaining batch
        if current_batch_texts:
            batch_content = "\n\n".join(current_batch_texts)
            if heading:
                batch_content = f"{heading}\n\n{batch_content}"

            chunks.append(
                {
                    "content": batch_content,
                    "tokens": current_tokens,
                    "ledd_ids": current_batch_ids.copy(),
                }
            )

        # Convert to LegalChunk objects with preserved metadata
        return [
            LegalChunk(
                chunk_id=f"{base_chunk_id}_sub_{i:03d}",
                content=chunk_data["content"],
                metadata={
                    **metadata,
                    "token_count": chunk_data["tokens"],
                    "requires_splitting": True,
                    "split_strategy": "xml_legalp_boundaries",
                    "parent_chunk_id": base_chunk_id,
                    "parent_total_tokens": sum(c["tokens"] for c in chunks),
                    "ledd_ids": chunk_data["ledd_ids"],
                },
                is_split=True,
                split_index=i,
                total_splits=len(chunks),
            )
            for i, chunk_data in enumerate(chunks)
        ]

    def _split_by_text_boundaries(
        self,
        content: str,
        base_chunk_id: str,
        metadata: dict,
        total_tokens: int,
    ) -> list[LegalChunk]:
        """Fall back to text-based recursive splitting when XML splitting fails.

        Uses hierarchical separators to preserve readability.

        Args:
            content: Text content to split
            base_chunk_id: Base chunk ID
            metadata: Base metadata
            total_tokens: Total tokens in content

        Returns:
            List of text-split LegalChunk objects
        """
        # Simple character-based splitting with overlap
        # This is a basic implementation - you could integrate langchain's
        # RecursiveCharacterTextSplitter here for more sophisticated splitting

        max_chars = self.max_tokens * 4  # Approximate chars per token
        overlap_chars = self.overlap_tokens * 4

        chunks = []
        start = 0

        while start < len(content):
            end = start + max_chars

            # Try to break at paragraph boundaries
            if end < len(content):
                # Look for paragraph break
                break_point = content.rfind("\n\n", start, end)
                if break_point == -1:
                    # Look for sentence break
                    break_point = content.rfind(". ", start, end)
                if break_point == -1:
                    # Look for any whitespace
                    break_point = content.rfind(" ", start, end)
                if break_point > start:
                    end = break_point + 1

            chunk_text = content[start:end].strip()
            if chunk_text:
                chunk_tokens = estimate_tokens(chunk_text)

                chunks.append(
                    LegalChunk(
                        chunk_id=f"{base_chunk_id}_sub_{len(chunks):03d}",
                        content=chunk_text,
                        metadata={
                            **metadata,
                            "token_count": chunk_tokens,
                            "requires_splitting": True,
                            "split_strategy": "text_boundaries",
                            "parent_chunk_id": base_chunk_id,
                            "parent_total_tokens": total_tokens,
                        },
                        is_split=True,
                        split_index=len(chunks),
                        total_splits=None,  # Don't know total until done
                    )
                )

            # Move start forward with overlap
            start = end - overlap_chars if overlap_chars > 0 else end

        # Update total_splits now that we know the count
        for chunk in chunks:
            chunk.total_splits = len(chunks)

        return chunks
