"""Chunking service for legal articles.

Responsible for splitting articles into appropriately-sized chunks.
Single Responsibility: Coordinate article chunking.
"""

from lovdata_pipeline.domain.models import ChunkMetadata
from lovdata_pipeline.domain.parsers.xml_chunker import LegalArticle
from lovdata_pipeline.domain.services.xml_parsing_service import ParsedArticle
from lovdata_pipeline.domain.splitters.recursive_splitter import XMLAwareRecursiveSplitter


class ChunkingService:
    """Service for chunking legal articles.

    Single Responsibility: Split articles into chunks that fit within token limits.
    """

    def __init__(self, max_tokens: int):
        """Initialize chunking service.

        Args:
            max_tokens: Maximum tokens per chunk
        """
        self._max_tokens = max_tokens
        self._splitter = XMLAwareRecursiveSplitter(max_tokens=max_tokens)

    def chunk_article(
        self,
        article: ParsedArticle,
        doc_id: str,
        dataset: str,
        source_hash: str = "",
    ) -> list[ChunkMetadata]:
        """Split an article into chunks.

        Args:
            article: Parsed article to chunk
            doc_id: Document identifier
            dataset: Dataset name
            source_hash: SHA256 hash of source file

        Returns:
            List of chunk metadata objects
        """
        # Convert ParsedArticle to LegalArticle format expected by splitter
        # Note: We don't parse paragraphs separately in current implementation
        legal_article = LegalArticle(
            article_id=article.article_id,
            content=article.content,
            paragraphs=[],  # Current implementation extracts text directly
            section_heading=article.heading,
            absolute_address=article.address,
            document_id=doc_id,
        )

        # Use the splitter to create chunks
        chunks = self._splitter.split_article(
            legal_article, dataset_name=dataset, source_hash=source_hash
        )

        return chunks
