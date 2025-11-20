"""Chunking service for legal articles.

Responsible for splitting articles into appropriately-sized chunks.
Single Responsibility: Coordinate article chunking.
"""

from pathlib import Path

from lovdata_pipeline.domain.models import ChunkMetadata
from lovdata_pipeline.domain.parsers.lovdata_chunker import LovdataChunker


class ChunkingService:
    """Service for chunking legal documents.

    Single Responsibility: Split legal documents into chunks that fit within token limits.
    Uses the new LovdataChunker with overlapping chunks optimized for RAG.
    """

    def __init__(
        self,
        target_tokens: int = 512,
        max_tokens: int = 8191,
        overlap_ratio: float = 0.15,
    ):
        """Initialize chunking service.

        Args:
            target_tokens: Target number of tokens per chunk (default: 512)
            max_tokens: Maximum tokens per chunk (default: 8191)
            overlap_ratio: Ratio of overlap between chunks (default: 0.15)
        """
        self._target_tokens = target_tokens
        self._max_tokens = max_tokens
        self._overlap_ratio = overlap_ratio
        self._chunker = LovdataChunker(
            target_tokens=target_tokens,
            max_tokens=max_tokens,
            overlap_ratio=overlap_ratio,
        )

    def chunk_file(
        self,
        xml_path: str | Path,
        doc_id: str,
        dataset: str,
        source_hash: str = "",
    ) -> list[ChunkMetadata]:
        """Chunk an entire XML file.

        Args:
            xml_path: Path to XML file
            doc_id: Document identifier
            dataset: Dataset name
            source_hash: SHA256 hash of source file

        Returns:
            List of chunk metadata objects
        """
        # Use the new chunker
        chunks = self._chunker.chunk(xml_path)

        # Convert Chunk objects to ChunkMetadata
        chunk_metadata_list = []
        for chunk in chunks:
            # Extract metadata fields
            section_heading = chunk.metadata.get("section_heading", "")
            if not section_heading:
                # Try paragraph title or document title
                section_heading = chunk.metadata.get("paragraph_title", "")
                if not section_heading:
                    section_heading = chunk.metadata.get("document_title", "")

            absolute_address = chunk.metadata.get("url", "")
            if not absolute_address:
                absolute_address = chunk.metadata.get("address", "")

            chunk_metadata = ChunkMetadata(
                chunk_id=f"{doc_id}_{chunk.chunk_id}",
                document_id=doc_id,
                dataset_name=dataset,
                content=chunk.text,
                token_count=chunk.token_count,
                section_heading=section_heading,
                absolute_address=absolute_address,
                split_reason="none",  # The new chunker doesn't track split reasons
                source_hash=source_hash,
            )
            chunk_metadata_list.append(chunk_metadata)

        return chunk_metadata_list
