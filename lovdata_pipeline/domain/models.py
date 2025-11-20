"""Domain models for Lovdata pipeline.

These are pure Python data structures with no Dagster dependencies.
Uses Pydantic for validation, serialization, and type safety.
"""

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, computed_field

FileStatus = Literal["added", "modified", "removed"]
SplitReason = Literal["none", "paragraph", "sentence", "token"]


class SyncStatistics(BaseModel):
    """Statistics from a lovlig sync operation.

    Attributes:
        files_added: Number of files added in this sync
        files_modified: Number of files modified in this sync
        files_removed: Number of files removed in this sync
        duration_seconds: Duration of the sync operation in seconds
    """

    files_added: int = Field(ge=0, description="Number of files added")
    files_modified: int = Field(ge=0, description="Number of files modified")
    files_removed: int = Field(ge=0, description="Number of files removed")
    duration_seconds: float = Field(default=0.0, ge=0.0, description="Sync duration in seconds")

    @computed_field  # type: ignore[misc]
    @property
    def total_changed(self) -> int:
        """Return total number of changed files (added + modified)."""
        return self.files_added + self.files_modified


class FileMetadata(BaseModel):
    """Metadata about a single file from lovlig state.

    Attributes:
        relative_path: Path relative to extracted data directory
        absolute_path: Absolute filesystem path
        file_hash: SHA256 hash of file contents
        dataset_name: Name of the dataset (e.g., 'gjeldende-lover')
        status: File status (added, modified, or removed)
        file_size_bytes: Size of file in bytes
        document_id: Document identifier extracted from filename
    """

    relative_path: str = Field(description="Relative path from extracted data dir")
    absolute_path: Path = Field(description="Absolute filesystem path")
    file_hash: str = Field(description="SHA256 hash of file contents")
    dataset_name: str = Field(description="Dataset name")
    status: FileStatus = Field(description="File status")
    file_size_bytes: int = Field(ge=0, description="File size in bytes")
    document_id: str = Field(description="Document identifier")

    model_config = {"arbitrary_types_allowed": True}

    def model_dump_custom(self) -> dict:
        """Convert to dictionary with Path as string.

        Returns:
            Dictionary representation of file metadata
        """
        data = self.model_dump()
        data["absolute_path"] = str(self.absolute_path)
        return data


class RemovalInfo(BaseModel):
    """Information about a removed file.

    Attributes:
        document_id: Document identifier
        relative_path: Path that was removed
        dataset_name: Name of the dataset
        last_hash: Last known hash of the file
    """

    document_id: str = Field(description="Document identifier")
    relative_path: str = Field(description="Relative path that was removed")
    dataset_name: str = Field(description="Dataset name")
    last_hash: str = Field(description="Last known hash")


class ChunkMetadata(BaseModel):
    """Metadata for a single legal document chunk.

    This model represents a chunk of text extracted from a Lovdata XML document.
    Chunks are created using XML-aware splitting that respects legal structure.

    Attributes:
        chunk_id: Unique identifier for this chunk
        document_id: ID of the source document
        dataset_name: Name of the dataset (e.g., 'gjeldende-lover.tar.bz2')
        content: The actual text content of the chunk
        token_count: Number of tokens in the content
        section_heading: Title/heading of the legal section
        absolute_address: Lovdata absolute address (e.g., NL/lov/1687-04-15/b1/k21/a15)
        split_reason: Why chunk was created (none=fits naturally, paragraph/sentence/token)
        parent_chunk_id: ID of parent chunk if this is a sub-chunk from splitting
    """

    chunk_id: str = Field(description="Unique identifier for this chunk")
    document_id: str = Field(description="Source document identifier")
    dataset_name: str = Field(
        default="", description="Dataset name (e.g., 'gjeldende-lover.tar.bz2')"
    )
    content: str = Field(description="Text content of the chunk")
    token_count: int = Field(ge=0, description="Number of tokens in content")
    section_heading: str = Field(default="", description="Legal section heading")
    absolute_address: str = Field(default="", description="Lovdata absolute address")
    split_reason: SplitReason = Field(default="none", description="Reason for chunk creation")
    parent_chunk_id: str | None = Field(
        default=None, description="Parent chunk ID if this is a sub-chunk"
    )
    source_hash: str = Field(default="", description="SHA256 hash of source file")

    @property
    def text(self) -> str:
        """Alias for content attribute.

        Provides compatibility for code expecting .text instead of .content.

        Returns:
            The chunk's text content
        """
        return self.content


class EnrichedChunk(ChunkMetadata):
    """Chunk with embedding and metadata for vector storage.

    Extends ChunkMetadata with embedding information for vector database indexing.

    Attributes:
        embedding: Vector embedding of the chunk content
        embedding_model: Name of the model used to generate the embedding
        embedded_at: Timestamp when the embedding was created
    """

    embedding: list[float] = Field(description="Vector embedding of the content")
    embedding_model: str = Field(description="Model used for embedding")
    embedded_at: str = Field(description="ISO timestamp when embedded")

    @property
    def metadata(self) -> dict[str, Any]:
        """Get metadata dict for vector DB storage.

        Returns:
            Dictionary containing all metadata fields for vector database
        """
        # Reconstruct file_path from dataset_name and document_id
        file_path = (
            f"data/extracted/{self.dataset_name}/{self.document_id}.xml"
            if self.dataset_name
            else ""
        )

        return {
            "document_id": self.document_id,
            "dataset_name": self.dataset_name,
            "file_path": file_path,
            "section_heading": self.section_heading,
            "absolute_address": self.absolute_address,
            "token_count": self.token_count,
            "split_reason": self.split_reason,
            "parent_chunk_id": self.parent_chunk_id,
            "embedded_at": self.embedded_at,
            "embedding_model": self.embedding_model,
            "chunk_id": self.chunk_id,
            "source_hash": self.source_hash,
        }
