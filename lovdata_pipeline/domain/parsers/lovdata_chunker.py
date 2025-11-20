"""Core Chunking Algorithm for Lovdata XML Documents.

Optimized for 512-token chunks with hierarchical structure preservation.
Three-tier fallback strategy:
1. Standard laws: legalArticle → legalP (ledd)
2. Change laws: section → grouped legalP
3. Simple laws: main → legalP
"""

import re
from dataclasses import dataclass
from pathlib import Path

import tiktoken
from lxml import etree


@dataclass
class Chunk:
    """Minimal chunk representation."""

    chunk_id: str
    text: str
    token_count: int
    metadata: dict  # Contains all structural/hierarchical info


class LovdataChunker:
    """Three-tier fallback chunking strategy for Lovdata XML documents.

    1. Standard laws: legalArticle → legalP (ledd)
    2. Change laws: section → grouped legalP
    3. Simple laws: main → legalP
    """

    def __init__(
        self,
        target_tokens: int = 512,
        max_tokens: int = 8191,
        overlap_ratio: float = 0.15,
    ) -> None:
        """Initialize the chunker.

        Args:
            target_tokens: Target number of tokens per chunk
            max_tokens: Maximum number of tokens per chunk
            overlap_ratio: Ratio of overlap between chunks (0.0-1.0)
        """
        self.encoding = tiktoken.get_encoding("cl100k_base")
        self.target = target_tokens
        self.max = max_tokens
        self.overlap = int(target_tokens * overlap_ratio)

    def chunk(self, xml_path: str | Path) -> list[Chunk]:
        """Main entry point - three-tier fallback.

        Args:
            xml_path: Path to XML file to chunk

        Returns:
            List of Chunk objects
        """
        tree = etree.parse(str(xml_path))
        root = tree.getroot()

        # Tier 1: Standard laws (paragraphs with ledd)
        chunks = self._chunk_standard(root)
        if chunks:
            return chunks

        # Tier 2: Change laws (legalP in sections)
        chunks = self._chunk_change_law(root)
        if chunks:
            return chunks

        # Tier 3: Simple laws (legalP under main)
        return self._chunk_simple(root)

    def _chunk_standard(self, root) -> list[Chunk]:
        """Standard modern laws: extract at ledd (legalP) level.

        Each ledd becomes a chunk with parent paragraph context.

        Args:
            root: XML root element

        Returns:
            List of chunks
        """
        chunks = []

        # Find all paragraphs (§)
        for article in root.xpath('//article[@class="legalArticle"]'):
            paragraph_ref = self._get_paragraph_ref(article)
            paragraph_title = self._get_paragraph_title(article)
            context = self._get_hierarchical_context(article, root)

            # Extract all ledd within this paragraph
            for idx, ledd in enumerate(article.xpath('.//article[@class="legalP"]'), 1):
                text = self._extract_ledd_text(ledd)
                tokens = self._count_tokens(text)

                # Check if within limits
                if tokens <= self.max:
                    chunk = self._create_chunk(
                        text=text,
                        tokens=tokens,
                        ledd_elem=ledd,
                        ledd_number=idx,
                        paragraph_ref=paragraph_ref,
                        paragraph_title=paragraph_title,
                        context=context,
                    )
                    chunks.append(chunk)
                else:
                    # Ledd too large - split further
                    sub_chunks = self._split_large_ledd(
                        ledd, text, idx, paragraph_ref, paragraph_title, context
                    )
                    chunks.extend(sub_chunks)

        return chunks

    def _chunk_change_law(self, root) -> list[Chunk]:
        """Change laws: group consecutive legalP under sections.

        Combine multiple legalP up to target token size.

        Args:
            root: XML root element

        Returns:
            List of chunks
        """
        chunks = []

        for section in root.xpath('//section[@class="section"]'):
            section_heading = self._get_section_heading(section)
            context = self._get_hierarchical_context(section, root)

            # Group legalP elements
            legalp_list = section.xpath('.//article[@class="legalP"]')
            if not legalp_list:
                continue

            # Accumulate legalP until target size reached
            buffer = []
            buffer_tokens = 0

            for legalp in legalp_list:
                text = self._extract_text(legalp)
                tokens = self._count_tokens(text)

                # Check if adding this legalP exceeds target
                if buffer_tokens + tokens > self.target and buffer:
                    # Create chunk from buffer
                    chunk = self._create_grouped_chunk(buffer, section_heading, context)
                    chunks.append(chunk)

                    # Reset buffer
                    buffer = []
                    buffer_tokens = 0

                buffer.append((legalp, text, tokens))
                buffer_tokens += tokens

            # Handle remaining buffer
            if buffer:
                chunk = self._create_grouped_chunk(buffer, section_heading, context)
                chunks.append(chunk)

        return chunks

    def _chunk_simple(self, root) -> list[Chunk]:
        """Simple/old laws: legalP directly under main.

        Extract each legalP as individual chunk.

        Args:
            root: XML root element

        Returns:
            List of chunks
        """
        chunks = []

        main = root.find('.//main[@class="documentBody"]')
        if main is None:
            return chunks

        doc_title = self._get_document_title(root)

        for idx, legalp in enumerate(main.xpath('./article[@class="legalP"]'), 1):
            text = self._extract_text(legalp)
            tokens = self._count_tokens(text)

            if tokens <= self.max:
                chunk = Chunk(
                    chunk_id=f"ledd-{idx}",
                    text=text,
                    token_count=tokens,
                    metadata={
                        "ledd_number": idx,
                        "document_title": doc_title,
                        "id": legalp.get("id", f"ledd-{idx}"),
                        "address": legalp.get("data-absoluteaddress", ""),
                        "url": legalp.get("data-lovdata-URL", ""),
                    },
                )
                chunks.append(chunk)
            else:
                # Split if too large
                sub_chunks = self._split_by_sentences(text, idx, doc_title)
                chunks.extend(sub_chunks)

        return chunks

    def _extract_ledd_text(self, ledd_elem) -> str:
        """Extract text from ledd, handling lists and continuations.

        Preserves structure: lists, leddfortsettelse, nested content.

        Args:
            ledd_elem: legalP XML element

        Returns:
            Extracted text with structure preserved
        """
        parts = []

        # Get direct text
        if ledd_elem.text:
            parts.append(ledd_elem.text.strip())

        # Process children
        for child in ledd_elem:
            if child.tag in ["ol", "ul"]:
                # Extract list with markers
                list_text = self._extract_list(child)
                parts.append(list_text)

            elif child.tag == "p" and "leddfortsettelse" in child.get("class", ""):
                # Continuation after list
                parts.append("".join(child.itertext()).strip())

            else:
                # Other content
                text = "".join(child.itertext()).strip()
                if text:
                    parts.append(text)

            # Get tail text
            if child.tail:
                parts.append(child.tail.strip())

        return " ".join(filter(None, parts))

    def _extract_list(self, list_elem) -> str:
        """Extract list with structure preserved.

        Args:
            list_elem: List XML element (ol or ul)

        Returns:
            List text with markers
        """
        items = []

        for li in list_elem.findall(".//li"):
            marker = li.get("data-name", "")
            text = "".join(li.itertext()).strip()
            if marker:
                items.append(f"{marker} {text}")
            else:
                items.append(text)

        return "\n".join(items)

    def _split_large_ledd(
        self,
        ledd_elem,
        text,
        ledd_num,
        paragraph_ref,
        paragraph_title,
        context,
    ) -> list[Chunk]:
        """Split ledd that exceeds max tokens.

        Strategy: split by lists first, then sentences with overlap.

        Args:
            ledd_elem: legalP XML element
            text: Extracted text
            ledd_num: Ledd number
            paragraph_ref: Paragraph reference (e.g., '§ 5')
            paragraph_title: Paragraph title
            context: Hierarchical context dict

        Returns:
            List of sub-chunks
        """
        # Check if contains lists
        has_lists = (
            ledd_elem.find(".//ol") is not None or ledd_elem.find(".//ul") is not None
        )

        if has_lists:
            return self._split_by_lists(
                ledd_elem, ledd_num, paragraph_ref, paragraph_title, context
            )
        else:
            return self._split_by_sentences_with_overlap(
                text, ledd_num, paragraph_ref, paragraph_title, context
            )

    def _split_by_lists(
        self,
        ledd_elem,
        ledd_num,
        paragraph_ref,
        paragraph_title,
        context,
    ) -> list[Chunk]:
        """Split ledd by list boundaries.

        Creates chunks: [pre-list text], [list], [post-list text]

        Args:
            ledd_elem: legalP XML element
            ledd_num: Ledd number
            paragraph_ref: Paragraph reference
            paragraph_title: Paragraph title
            context: Hierarchical context dict

        Returns:
            List of chunks split by lists
        """
        chunks = []
        parts = []

        current_text = []

        # Walk through children
        for child in ledd_elem:
            if child.tag in ["ol", "ul"]:
                # Save accumulated text before list
                if current_text:
                    parts.append(" ".join(current_text))
                    current_text = []

                # Add list as separate part
                list_text = self._extract_list(child)
                parts.append(list_text)
            else:
                # Accumulate non-list text
                text = "".join(child.itertext()).strip()
                if text:
                    current_text.append(text)

        # Add remaining text
        if current_text:
            parts.append(" ".join(current_text))

        # Create chunks from parts
        for idx, part in enumerate(parts, 1):
            tokens = self._count_tokens(part)

            if tokens < self.max:
                chunk = Chunk(
                    chunk_id=f"{paragraph_ref}-ledd{ledd_num}-part{idx}",
                    text=part,
                    token_count=tokens,
                    metadata={
                        "paragraph_ref": paragraph_ref,
                        "paragraph_title": paragraph_title,
                        "ledd_number": ledd_num,
                        "part": idx,
                        **context,
                    },
                )
                chunks.append(chunk)

        return chunks

    def _split_by_sentences_with_overlap(
        self,
        text,
        ledd_num,
        paragraph_ref,
        paragraph_title,
        context,
    ) -> list[Chunk]:
        """Split text into overlapping sentence-based chunks.

        Maintains 15% overlap between chunks.

        Args:
            text: Text to split
            ledd_num: Ledd number
            paragraph_ref: Paragraph reference
            paragraph_title: Paragraph title
            context: Hierarchical context dict

        Returns:
            List of overlapping chunks
        """
        # Split into sentences (Norwegian-aware)
        sentences = re.split(r"(?<=[.!?])\s+", text)
        sentences = [s.strip() for s in sentences if s.strip()]

        chunks = []
        overlap_count = max(1, int(len(sentences) * self.overlap / self.target))

        i = 0
        chunk_idx = 1

        while i < len(sentences):
            # Accumulate sentences up to target
            chunk_sentences = []
            chunk_tokens = 0

            j = i
            while j < len(sentences):
                sent = sentences[j]
                sent_tokens = self._count_tokens(sent)

                if chunk_tokens + sent_tokens <= self.target:
                    chunk_sentences.append(sent)
                    chunk_tokens += sent_tokens
                    j += 1
                else:
                    break

            # Create chunk
            if chunk_sentences:
                chunk_text = " ".join(chunk_sentences)

                chunk = Chunk(
                    chunk_id=f"{paragraph_ref}-ledd{ledd_num}-{chunk_idx}",
                    text=chunk_text,
                    token_count=chunk_tokens,
                    metadata={
                        "paragraph_ref": paragraph_ref,
                        "paragraph_title": paragraph_title,
                        "ledd_number": ledd_num,
                        "chunk_part": chunk_idx,
                        **context,
                    },
                )
                chunks.append(chunk)
                chunk_idx += 1

            # Move forward with overlap
            i = max(i + 1, j - overlap_count)

        return chunks

    def _split_by_sentences(self, text: str, idx: int, doc_title: str) -> list[Chunk]:
        """Split text by sentences for simple laws.

        Args:
            text: Text to split
            idx: Ledd index
            doc_title: Document title

        Returns:
            List of sentence-based chunks
        """
        sentences = re.split(r"(?<=[.!?])\s+", text)
        sentences = [s.strip() for s in sentences if s.strip()]

        chunks = []
        chunk_idx = 1

        for sent in sentences:
            tokens = self._count_tokens(sent)
            if tokens <= self.max:
                chunk = Chunk(
                    chunk_id=f"ledd-{idx}-{chunk_idx}",
                    text=sent,
                    token_count=tokens,
                    metadata={
                        "ledd_number": idx,
                        "document_title": doc_title,
                        "chunk_part": chunk_idx,
                    },
                )
                chunks.append(chunk)
                chunk_idx += 1

        return chunks

    def _create_chunk(
        self,
        text,
        tokens,
        ledd_elem,
        ledd_number,
        paragraph_ref,
        paragraph_title,
        context,
    ) -> Chunk:
        """Create chunk with full metadata.

        Args:
            text: Chunk text
            tokens: Token count
            ledd_elem: legalP XML element
            ledd_number: Ledd number
            paragraph_ref: Paragraph reference
            paragraph_title: Paragraph title
            context: Hierarchical context dict

        Returns:
            Chunk object with metadata
        """
        return Chunk(
            chunk_id=ledd_elem.get("id", f"{paragraph_ref}-ledd{ledd_number}"),
            text=text,
            token_count=tokens,
            metadata={
                "paragraph_ref": paragraph_ref,
                "paragraph_title": paragraph_title,
                "ledd_number": ledd_number,
                "address": ledd_elem.get("data-absoluteaddress", ""),
                "url": ledd_elem.get("data-lovdata-URL", ""),
                "cross_refs": self._get_cross_refs(ledd_elem),
                **context,
            },
        )

    def _create_grouped_chunk(
        self,
        legalp_buffer,
        section_heading,
        context,
    ) -> Chunk:
        """Create chunk from multiple grouped legalP elements.

        Args:
            legalp_buffer: List of (legalp_elem, text, tokens) tuples
            section_heading: Section heading text
            context: Hierarchical context dict

        Returns:
            Grouped chunk
        """
        combined_text = "\n\n".join([text for _, text, _ in legalp_buffer])
        total_tokens = sum([tokens for _, _, tokens in legalp_buffer])

        first_id = legalp_buffer[0][0].get("id", "unknown")

        return Chunk(
            chunk_id=f"section-{first_id}",
            text=combined_text,
            token_count=total_tokens,
            metadata={
                "section_heading": section_heading,
                "legalp_count": len(legalp_buffer),
                **context,
            },
        )

    # Helper methods

    def _count_tokens(self, text: str) -> int:
        """Count tokens using tiktoken.

        Args:
            text: Text to count

        Returns:
            Number of tokens
        """
        return len(self.encoding.encode(text))

    def _extract_text(self, elem) -> str:
        """Extract all text from element.

        Args:
            elem: XML element

        Returns:
            Extracted text
        """
        return "".join(elem.itertext()).strip()

    def _get_paragraph_ref(self, article_elem) -> str:
        """Extract § reference (e.g., '§ 5').

        Args:
            article_elem: legalArticle XML element

        Returns:
            Paragraph reference
        """
        header = article_elem.find('.//span[@class="legalArticleValue"]')
        return "".join(header.itertext()).strip() if header is not None else ""

    def _get_paragraph_title(self, article_elem) -> str | None:
        """Extract paragraph title if exists.

        Args:
            article_elem: legalArticle XML element

        Returns:
            Paragraph title or None
        """
        title = article_elem.find('.//span[@class="legalArticleTitle"]')
        return "".join(title.itertext()).strip() if title is not None else None

    def _get_section_heading(self, section_elem) -> str:
        """Extract section heading.

        Args:
            section_elem: section XML element

        Returns:
            Section heading text
        """
        for tag in ["h2", "h3", "h4"]:
            heading = section_elem.find(f".//{tag}")
            if heading is not None:
                return "".join(heading.itertext()).strip()
        return ""

    def _get_document_title(self, root) -> str:
        """Extract document title from h1.

        Args:
            root: XML root element

        Returns:
            Document title
        """
        h1 = root.find(".//h1")
        return "".join(h1.itertext()).strip() if h1 is not None else ""

    def _get_hierarchical_context(self, elem, root) -> dict:
        """Walk up tree to collect chapter/section hierarchy.

        Args:
            elem: Current XML element
            root: XML root element

        Returns:
            Context dict with document title, chapter path, section heading
        """
        context = {
            "document_title": self._get_document_title(root),
            "chapter_path": [],
            "section_heading": "",
        }

        current = elem.getparent()
        while current is not None:
            if current.get("class") == "section":
                heading = self._get_section_heading(current)
                if heading:
                    if not context["section_heading"]:
                        context["section_heading"] = heading
                    context["chapter_path"].insert(0, heading)

            current = current.getparent()

        return context

    def _get_cross_refs(self, elem) -> list[str]:
        """Extract cross-references (href values).

        Args:
            elem: XML element

        Returns:
            List of href values
        """
        return [a.get("href") for a in elem.findall(".//a[@href]")]
