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
    """Statistics from a lovlig sync operation."""

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
    """Metadata about a single file from lovlig state."""

    relative_path: str = Field(description="Relative path from extracted data dir")
    absolute_path: Path = Field(description="Absolute filesystem path")
    file_hash: str = Field(description="SHA256 hash of file contents")
    dataset_name: str = Field(description="Dataset name")
    status: FileStatus = Field(description="File status")
    file_size_bytes: int = Field(ge=0, description="File size in bytes")
    document_id: str = Field(description="Document identifier")

    model_config = {"arbitrary_types_allowed": True}

    def model_dump_custom(self) -> dict:
        """Convert to dictionary with Path as string."""
        data = self.model_dump()
        data["absolute_path"] = str(self.absolute_path)
        return data


class RemovalInfo(BaseModel):
    """Information about a removed file."""

    document_id: str = Field(description="Document identifier")
    relative_path: str = Field(description="Relative path that was removed")
    dataset_name: str = Field(description="Dataset name")
    last_hash: str = Field(description="Last known hash")


class ChunkMetadata(BaseModel):
    """Metadata for a single legal document chunk.

    Represents a chunk of text extracted from a Lovdata XML document using
    XML-aware splitting that respects legal structure.
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
    cross_refs: list[str] = Field(
        default_factory=list, description="Cross-references to other laws (href values)"
    )

    @property
    def text(self) -> str:
        """Alias for content attribute for compatibility."""
        return self.content


class EnrichedChunk(ChunkMetadata):
    """Chunk with embedding vector for vector storage.

    Extends ChunkMetadata with embedding information for vector database indexing.
    """

    embedding: list[float] = Field(description="Vector embedding of the content")
    embedding_model: str = Field(description="Model used for embedding")
    embedded_at: str = Field(description="ISO timestamp when embedded")

    @property
    def metadata(self) -> dict[str, Any]:
        """Get metadata dict for vector DB storage.

        ChromaDB only accepts str, int, float, bool, or None as metadata values.
        Lists are not supported, so we convert cross_refs to a comma-separated string.
        """
        # Reconstruct file_path from dataset_name and document_id
        file_path = (
            f"data/extracted/{self.dataset_name}/{self.document_id}.xml"
            if self.dataset_name
            else ""
        )

        # Convert cross_refs list to comma-separated string for ChromaDB compatibility
        cross_refs_str = ",".join(self.cross_refs) if self.cross_refs else ""

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
            "cross_refs": cross_refs_str,
        }


# ============================================================================
# Chunking Models
# ============================================================================


class Chunk(BaseModel):
    """Minimal chunk representation from chunker."""

    chunk_id: str = Field(description="Unique identifier for this chunk")
    text: str = Field(description="Text content of the chunk")
    token_count: int = Field(ge=0, description="Number of tokens in the text")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Structural/hierarchical info"
    )


# ============================================================================
# File Processing Models
# ============================================================================


class FileInfo(BaseModel):
    """Information about a file to process."""

    doc_id: str = Field(description="Document identifier")
    path: Path = Field(description="Path to the file")
    dataset: str = Field(description="Dataset name")
    hash: str = Field(description="SHA256 hash of file")

    model_config = {"arbitrary_types_allowed": True}


class FileProcessingResult(BaseModel):
    """Result of processing a single file."""

    success: bool = Field(description="Whether processing succeeded")
    chunk_count: int = Field(ge=0, description="Number of chunks created")
    error_message: str | None = Field(default=None, description="Error message if failed")


# ============================================================================
# Pipeline Orchestration Models
# ============================================================================


class PipelineConfig(BaseModel):
    """Configuration for pipeline execution."""

    data_dir: Path = Field(description="Root data directory")
    dataset_filter: str = Field(description="Dataset filter pattern")
    force: bool = Field(default=False, description="Force reprocessing")
    limit: int | None = Field(
        default=None, description="Limit number of files to process (for testing)"
    )

    model_config = {"arbitrary_types_allowed": True}


class PipelineResult(BaseModel):
    """Result of pipeline execution."""

    processed: int = Field(ge=0, description="Number of documents processed")
    failed: int = Field(ge=0, description="Number of documents failed")
    removed: int = Field(ge=0, description="Number of documents removed")


# ============================================================================
# Lovlig Integration Models
# ============================================================================


class LovligFileInfo(BaseModel):
    """Information about a file from lovlig state."""

    doc_id: str = Field(description="Document identifier")
    path: Path = Field(description="Absolute path to file")
    hash: str = Field(description="SHA256 hash of file")
    dataset: str = Field(description="Dataset name")

    model_config = {"arbitrary_types_allowed": True}


class LovligRemovedFileInfo(BaseModel):
    """Information about a removed file from lovlig state."""

    doc_id: str = Field(description="Document identifier")
    dataset: str = Field(description="Dataset name")


class LovligSyncStats(BaseModel):
    """Statistics from lovlig sync operation."""

    added: int = Field(ge=0, description="Number of files added")
    modified: int = Field(ge=0, description="Number of files modified")
    removed: int = Field(ge=0, description="Number of files removed")


# ============================================================================
# State Management Models
# ============================================================================


class ProcessedDocumentInfo(BaseModel):
    """Information about a successfully processed document."""

    hash: str = Field(description="SHA256 hash of document")
    at: str = Field(description="ISO timestamp when processed")


class FailedDocumentInfo(BaseModel):
    """Information about a failed document."""

    hash: str = Field(description="SHA256 hash of document")
    error: str = Field(description="Error message")
    at: str = Field(description="ISO timestamp when failed")


class ProcessingStateData(BaseModel):
    """Complete processing state structure."""

    processed: dict[str, ProcessedDocumentInfo] = Field(default_factory=dict)
    failed: dict[str, FailedDocumentInfo] = Field(default_factory=dict)
