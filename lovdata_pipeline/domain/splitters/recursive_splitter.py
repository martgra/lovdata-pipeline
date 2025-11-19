"""XML-aware recursive splitter for legal documents.

This module implements a three-tier splitting strategy:
1. Split at legalP paragraph boundaries (best for semantics)
2. Split at Norwegian sentence boundaries (when paragraphs are too large)
3. Hard split by token boundaries (last resort for extremely long sentences)
"""

import re

from lovdata_pipeline.domain.models import ChunkMetadata, SplitReason
from lovdata_pipeline.domain.parsers.xml_chunker import LegalArticle
from lovdata_pipeline.domain.splitters.token_counter import TokenCounter


class XMLAwareRecursiveSplitter:
    """Split legal articles into chunks using XML structure awareness.

    This splitter attempts to preserve legal semantics by splitting at
    natural boundaries in this order:
    1. legalP paragraphs (XML structure)
    2. Sentence boundaries (Norwegian-aware)
    3. Token boundaries (mechanical fallback)
    """

    def __init__(self, max_tokens: int = 6800, encoding: str = "cl100k_base") -> None:
        """Initialize the splitter.

        Args:
            max_tokens: Maximum tokens per chunk
            encoding: Tiktoken encoding to use
        """
        self.max_tokens = max_tokens
        self.token_counter = TokenCounter(encoding_name=encoding)
        # Norwegian sentence regex: period/question/exclamation followed by space and capital
        self.sentence_pattern = re.compile(r"(?<=[.!?])\s+(?=[A-ZÆØÅ])")

    def split_article(self, article: LegalArticle, dataset_name: str = "") -> list[ChunkMetadata]:
        """Split a legal article into chunks.

        Args:
            article: LegalArticle to split
            dataset_name: Name of the dataset (e.g., 'gjeldende-lover.tar.bz2')

        Returns:
            List of ChunkMetadata objects
        """
        token_count = self.token_counter.count_tokens(article.content)

        # If it fits, return as single chunk
        if token_count <= self.max_tokens:
            return [
                ChunkMetadata(
                    chunk_id=f"{article.document_id}_{article.article_id}",
                    document_id=article.document_id,
                    dataset_name=dataset_name,
                    content=article.content,
                    token_count=token_count,
                    section_heading=article.section_heading,
                    absolute_address=article.absolute_address,
                    split_reason="none",
                )
            ]

        # Try paragraph-level splitting first
        if article.paragraphs:
            chunks = self._split_by_paragraphs(article, dataset_name)
            if chunks:
                return chunks

        # Fall back to sentence splitting
        chunks = self._split_by_sentences(article, dataset_name)
        if chunks:
            return chunks

        # Last resort: hard token split
        return self._split_by_tokens(article, dataset_name)

    def _split_by_paragraphs(
        self, article: LegalArticle, dataset_name: str = ""
    ) -> list[ChunkMetadata]:
        """Split article by grouping legalP paragraphs.

        Args:
            article: LegalArticle to split
            dataset_name: Name of the dataset

        Returns:
            List of ChunkMetadata objects or empty list if splitting fails
        """
        chunks = []
        current_paragraphs = []
        current_tokens = 0
        chunk_index = 0

        for paragraph in article.paragraphs:
            para_tokens = self.token_counter.count_tokens(paragraph)

            # If single paragraph is too large, need to split it further
            if para_tokens > self.max_tokens:
                # Save accumulated paragraphs first
                if current_paragraphs:
                    content = " ".join(current_paragraphs)
                    chunks.append(
                        self._create_chunk_metadata(
                            article, content, chunk_index, "paragraph", current_tokens
                        )
                    )
                    chunk_index += 1
                    current_paragraphs = []
                    current_tokens = 0

                # Split this large paragraph by sentences
                para_chunks = self._split_text_by_sentences(
                    paragraph, article, chunk_index, dataset_name
                )
                chunks.extend(para_chunks)
                chunk_index += len(para_chunks)
                continue

            # Check if adding this paragraph would exceed limit
            if current_tokens + para_tokens > self.max_tokens:
                # Save current chunk
                if current_paragraphs:
                    content = " ".join(current_paragraphs)
                    chunks.append(
                        self._create_chunk_metadata(
                            article, content, chunk_index, "paragraph", current_tokens
                        )
                    )
                    chunk_index += 1

                # Start new chunk with this paragraph
                current_paragraphs = [paragraph]
                current_tokens = para_tokens
            else:
                # Add to current chunk
                current_paragraphs.append(paragraph)
                current_tokens += para_tokens

        # Don't forget the last chunk
        if current_paragraphs:
            content = " ".join(current_paragraphs)
            chunks.append(
                self._create_chunk_metadata(
                    article, content, chunk_index, "paragraph", current_tokens, dataset_name
                )
            )

        return chunks

    def _split_by_sentences(
        self, article: LegalArticle, dataset_name: str = ""
    ) -> list[ChunkMetadata]:
        """Split article by Norwegian sentence boundaries.

        Args:
            article: LegalArticle to split
            dataset_name: Name of the dataset

        Returns:
            List of ChunkMetadata objects
        """
        return self._split_text_by_sentences(article.content, article, 0, dataset_name)

    def _split_text_by_sentences(
        self, text: str, article: LegalArticle, start_index: int, dataset_name: str = ""
    ) -> list[ChunkMetadata]:
        """Split text by sentence boundaries.

        Args:
            text: Text to split
            article: Source article for metadata
            start_index: Starting chunk index
            dataset_name: Name of the dataset

        Returns:
            List of ChunkMetadata objects
        """
        # Split into sentences
        sentences = self.sentence_pattern.split(text)
        if not sentences:
            return []

        chunks = []
        current_sentences = []
        current_tokens = 0
        chunk_index = start_index

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            sent_tokens = self.token_counter.count_tokens(sentence)

            # If single sentence is too large, hard split it
            if sent_tokens > self.max_tokens:
                # Save accumulated sentences first
                if current_sentences:
                    content = " ".join(current_sentences)
                    chunks.append(
                        self._create_chunk_metadata(
                            article, content, chunk_index, "sentence", current_tokens, dataset_name
                        )
                    )
                    chunk_index += 1
                    current_sentences = []
                    current_tokens = 0

                # Hard split this sentence
                sent_chunks = self._split_text_by_tokens(
                    sentence, article, chunk_index, dataset_name
                )
                chunks.extend(sent_chunks)
                chunk_index += len(sent_chunks)
                continue

            # Check if adding this sentence would exceed limit
            if current_tokens + sent_tokens > self.max_tokens:
                # Save current chunk
                if current_sentences:
                    content = " ".join(current_sentences)
                    chunks.append(
                        self._create_chunk_metadata(
                            article, content, chunk_index, "sentence", current_tokens, dataset_name
                        )
                    )
                    chunk_index += 1

                # Start new chunk with this sentence
                current_sentences = [sentence]
                current_tokens = sent_tokens
            else:
                # Add to current chunk
                current_sentences.append(sentence)
                current_tokens += sent_tokens

        # Don't forget the last chunk
        if current_sentences:
            content = " ".join(current_sentences)
            chunks.append(
                self._create_chunk_metadata(
                    article, content, chunk_index, "sentence", current_tokens, dataset_name
                )
            )

        return chunks

    def _split_by_tokens(
        self, article: LegalArticle, dataset_name: str = ""
    ) -> list[ChunkMetadata]:
        """Hard split article by token boundaries (last resort).

        Args:
            article: LegalArticle to split
            dataset_name: Name of the dataset

        Returns:
            List of ChunkMetadata objects
        """
        return self._split_text_by_tokens(article.content, article, 0, dataset_name)

    def _split_text_by_tokens(
        self, text: str, article: LegalArticle, start_index: int, dataset_name: str = ""
    ) -> list[ChunkMetadata]:
        """Hard split text by token boundaries.

        Args:
            text: Text to split
            article: Source article for metadata
            start_index: Starting chunk index
            dataset_name: Name of the dataset

        Returns:
            List of ChunkMetadata objects
        """
        text_chunks = self.token_counter.split_by_tokens(text, self.max_tokens)
        chunks = []

        for i, chunk_text in enumerate(text_chunks):
            token_count = self.token_counter.count_tokens(chunk_text)
            chunks.append(
                self._create_chunk_metadata(
                    article, chunk_text, start_index + i, "token", token_count, dataset_name
                )
            )

        return chunks

    def _create_chunk_metadata(
        self,
        article: LegalArticle,
        content: str,
        chunk_index: int,
        split_reason: SplitReason,
        token_count: int | None = None,
        dataset_name: str = "",
    ) -> ChunkMetadata:
        """Create a ChunkMetadata object.

        Args:
            article: Source article
            content: Chunk content
            chunk_index: Index of this chunk
            split_reason: Reason for splitting
            token_count: Precomputed token count (if None, will compute)
            dataset_name: Name of the dataset

        Returns:
            ChunkMetadata object
        """
        if token_count is None:
            token_count = self.token_counter.count_tokens(content)

        base_id = f"{article.document_id}_{article.article_id}"
        chunk_id = base_id if chunk_index == 0 else f"{base_id}_sub_{chunk_index:03d}"

        return ChunkMetadata(
            chunk_id=chunk_id,
            document_id=article.document_id,
            dataset_name=dataset_name,
            content=content,
            token_count=token_count,
            section_heading=article.section_heading,
            absolute_address=article.absolute_address,
            split_reason=split_reason,
            parent_chunk_id=base_id if chunk_index > 0 else None,
        )
