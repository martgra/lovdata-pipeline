"""Pipeline manifest for tracking document processing state across all stages.

This module provides a unified view of document processing, tracking:
- Which stage each document is in (chunking, embedding, indexing)
- Success/failure status with error details
- Processing timestamps and metadata
- Version history for each document

Addresses functional requirements:
- Req 3: Local pipeline manifest
- Req 6: Stage model tracking
- Req 7: Per-stage checkpointing
- Req 8: Per-document failure recovery
- Req 21: Auditability
"""

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

from lovdata_pipeline.utils.file_ops import atomic_write_json


class StageStatus(str, Enum):
    """Status of a pipeline stage for a document."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class IndexStatus(str, Enum):
    """Status of a document in the vector index."""

    INDEXED = "indexed"  # All vectors current in index
    PENDING = "pending"  # Needs indexing (new or modified)
    UPDATING = "updating"  # Currently being indexed
    FAILED = "failed"  # Indexing failed
    DELETED = "deleted"  # Removed from index


class ErrorClassification(str, Enum):
    """Classification of errors for retry logic."""

    TRANSIENT = "transient"  # Retriable (network, rate limit, etc.)
    PERMANENT = "permanent"  # Requires manual intervention (parse error, etc.)


@dataclass
class ErrorInfo:
    """Information about a stage failure."""

    type: str  # Exception class name
    message: str  # Error message
    classification: ErrorClassification
    traceback: str | None = None
    retry_count: int = 0
    max_retries: int = 3
    last_retry_at: str | None = None
    retry_after: str | None = None  # For rate limits


@dataclass
class StageOutput:
    """Output information from a completed stage."""

    # Common fields
    chunk_count: int | None = None
    output_file: str | None = None
    line_range: tuple[int, int] | None = None

    # Indexing-specific
    index_name: str | None = None
    vector_ids: list[str] | None = None


@dataclass
class StageInfo:
    """Information about a single pipeline stage for a document."""

    status: StageStatus
    started_at: str | None = None
    completed_at: str | None = None
    failed_at: str | None = None
    error: ErrorInfo | None = None
    output: StageOutput | None = None
    metadata: dict | None = None


@dataclass
class DocumentVersion:
    """Information about a specific version of a document."""

    file_hash: str
    discovered_at: str
    file_size_bytes: int
    stages: dict[str, StageInfo] = field(default_factory=dict)
    current_stage: str | None = None
    index_status: IndexStatus = IndexStatus.PENDING


@dataclass
class DocumentState:
    """Complete state for a document across all versions."""

    document_id: str
    dataset_name: str
    relative_path: str
    current_version: DocumentVersion
    version_history: list[DocumentVersion] = field(default_factory=list)


@dataclass
class ManifestSummary:
    """Summary statistics for the manifest."""

    total_documents: int
    by_stage: dict[str, int]
    by_index_status: dict[str, int]
    last_updated: str


class PipelineManifest:
    """Unified pipeline manifest tracking all document processing state.

    This class provides:
    - Single source of truth for document processing state
    - Stage-level tracking (chunking → embedding → indexing)
    - Error tracking with transient/permanent classification
    - Version history for each document
    - Auditability with timestamps

    Example:
        >>> manifest = PipelineManifest.load()
        >>> manifest.start_stage("doc-123", "hash-abc", "chunking")
        >>> manifest.complete_stage("doc-123", "hash-abc", "chunking",
        ...                         output={"chunk_count": 45})
        >>> manifest.save()
    """

    def __init__(self, manifest_file: Path):
        """Initialize manifest.

        Args:
            manifest_file: Path to manifest JSON file
        """
        self.manifest_file = manifest_file
        self.documents: dict[str, DocumentState] = {}
        self.version = "1.0.0"
        self.last_updated = datetime.now(UTC).isoformat()

    @classmethod
    def load(cls, manifest_file: Path | None = None) -> "PipelineManifest":
        """Load manifest from file.

        Args:
            manifest_file: Optional path to manifest file

        Returns:
            Loaded manifest instance
        """
        if manifest_file is None:
            from lovdata_pipeline.config.settings import get_settings

            settings = get_settings()
            manifest_file = settings.data_dir / "pipeline_manifest.json"

        manifest = cls(manifest_file)

        if not manifest_file.exists():
            return manifest

        try:
            with open(manifest_file) as f:
                data = json.load(f)

            manifest.version = data.get("version", "1.0.0")
            manifest.last_updated = data.get("last_updated", manifest.last_updated)

            # Deserialize documents
            for doc_id, doc_data in data.get("documents", {}).items():
                manifest.documents[doc_id] = manifest._deserialize_document(doc_data)

            return manifest

        except (json.JSONDecodeError, OSError):
            # Return empty manifest on error
            return manifest

    def save(self) -> None:
        """Save manifest to file atomically."""
        self.last_updated = datetime.now(UTC).isoformat()

        # Serialize to JSON
        data = {
            "version": self.version,
            "last_updated": self.last_updated,
            "documents": {
                doc_id: self._serialize_document(doc_state)
                for doc_id, doc_state in self.documents.items()
            },
            "summary": self._compute_summary(),
        }

        atomic_write_json(self.manifest_file, data)

    def get_document(self, document_id: str) -> DocumentState | None:
        """Get state for a document.

        Args:
            document_id: Document identifier

        Returns:
            Document state or None if not found
        """
        return self.documents.get(document_id)

    def ensure_document(
        self,
        document_id: str,
        dataset_name: str,
        relative_path: str,
        file_hash: str,
        file_size_bytes: int,
    ) -> DocumentState:
        """Ensure document exists in manifest, creating if needed.

        Args:
            document_id: Document identifier
            dataset_name: Dataset name
            relative_path: Relative file path
            file_hash: File content hash
            file_size_bytes: File size in bytes

        Returns:
            Document state (existing or newly created)
        """
        doc = self.documents.get(document_id)

        if doc is None:
            # Create new document
            doc = DocumentState(
                document_id=document_id,
                dataset_name=dataset_name,
                relative_path=relative_path,
                current_version=DocumentVersion(
                    file_hash=file_hash,
                    discovered_at=datetime.now(UTC).isoformat(),
                    file_size_bytes=file_size_bytes,
                ),
            )
            self.documents[document_id] = doc

        elif doc.current_version.file_hash != file_hash:
            # File changed - archive old version and create new
            doc.version_history.append(doc.current_version)
            doc.current_version = DocumentVersion(
                file_hash=file_hash,
                discovered_at=datetime.now(UTC).isoformat(),
                file_size_bytes=file_size_bytes,
            )

        return doc

    def start_stage(
        self,
        document_id: str,
        file_hash: str,
        stage: str,
    ) -> None:
        """Mark stage as started for a document.

        Args:
            document_id: Document identifier
            file_hash: File content hash (for verification)
            stage: Stage name (e.g., 'chunking', 'embedding', 'indexing')
        """
        doc = self.documents.get(document_id)
        if doc is None or doc.current_version.file_hash != file_hash:
            raise ValueError(f"Document {document_id} with hash {file_hash} not found")

        doc.current_version.stages[stage] = StageInfo(
            status=StageStatus.IN_PROGRESS,
            started_at=datetime.now(UTC).isoformat(),
        )
        doc.current_version.current_stage = stage

    def complete_stage(
        self,
        document_id: str,
        file_hash: str,
        stage: str,
        output: dict | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Mark stage as completed for a document.

        Args:
            document_id: Document identifier
            file_hash: File content hash (for verification)
            stage: Stage name
            output: Stage output information
            metadata: Additional metadata
        """
        doc = self.documents.get(document_id)
        if doc is None or doc.current_version.file_hash != file_hash:
            raise ValueError(f"Document {document_id} with hash {file_hash} not found")

        stage_info = doc.current_version.stages.get(stage)
        if stage_info is None:
            stage_info = StageInfo(status=StageStatus.IN_PROGRESS)
            doc.current_version.stages[stage] = stage_info

        stage_info.status = StageStatus.COMPLETED
        stage_info.completed_at = datetime.now(UTC).isoformat()
        if output:
            stage_info.output = StageOutput(**output)
        if metadata:
            stage_info.metadata = metadata

    def fail_stage(
        self,
        document_id: str,
        file_hash: str,
        stage: str,
        error_type: str,
        error_message: str,
        classification: ErrorClassification,
        traceback: str | None = None,
        retry_after: str | None = None,
    ) -> None:
        """Mark stage as failed for a document.

        Args:
            document_id: Document identifier
            file_hash: File content hash (for verification)
            stage: Stage name
            error_type: Exception class name
            error_message: Error message
            classification: Error classification (transient/permanent)
            traceback: Optional stack trace
            retry_after: Optional timestamp for when to retry
        """
        doc = self.documents.get(document_id)
        if doc is None or doc.current_version.file_hash != file_hash:
            raise ValueError(f"Document {document_id} with hash {file_hash} not found")

        stage_info = doc.current_version.stages.get(stage)
        if stage_info is None:
            stage_info = StageInfo(status=StageStatus.IN_PROGRESS)
            doc.current_version.stages[stage] = stage_info

        # Update or create error info
        if stage_info.error:
            stage_info.error.retry_count += 1
            stage_info.error.last_retry_at = datetime.now(UTC).isoformat()
        else:
            stage_info.error = ErrorInfo(
                type=error_type,
                message=error_message,
                classification=classification,
                traceback=traceback,
                retry_count=1,
                retry_after=retry_after,
            )

        stage_info.status = StageStatus.FAILED
        stage_info.failed_at = datetime.now(UTC).isoformat()

        # Update index status if this is a final failure
        if (
            stage_info.error.classification == ErrorClassification.PERMANENT
            or stage_info.error.retry_count >= stage_info.error.max_retries
        ):
            doc.current_version.index_status = IndexStatus.FAILED

    def set_index_status(
        self,
        document_id: str,
        status: IndexStatus,
    ) -> None:
        """Set index status for a document.

        Args:
            document_id: Document identifier
            status: New index status
        """
        doc = self.documents.get(document_id)
        if doc is None:
            raise ValueError(f"Document {document_id} not found")

        doc.current_version.index_status = status

    def is_stage_completed(self, document_id: str, stage: str) -> bool:
        """Check if a stage is completed for a document.

        Args:
            document_id: Document identifier
            stage: Stage name

        Returns:
            True if stage is completed, False otherwise
        """
        doc = self.documents.get(document_id)
        if doc is None:
            return False

        stage_info = doc.current_version.stages.get(stage)
        return stage_info is not None and stage_info.status == StageStatus.COMPLETED

    def get_unprocessed_files_for_stage(
        self, stage: str, all_files: list[tuple[str, str, str]]
    ) -> list[tuple[str, str, str]]:
        """Get files that need processing for a specific stage.

        Args:
            stage: Stage name (e.g., 'chunking', 'embedding')
            all_files: List of (document_id, file_hash, file_path) tuples

        Returns:
            Filtered list of files that need this stage
        """
        unprocessed = []
        for doc_id, file_hash, file_path in all_files:
            doc = self.documents.get(doc_id)

            # Process if document not in manifest
            if doc is None:
                unprocessed.append((doc_id, file_hash, file_path))
                continue

            # Process if hash changed (new version)
            if doc.current_version.file_hash != file_hash:
                unprocessed.append((doc_id, file_hash, file_path))
                continue

            # Process if stage not completed
            if not self.is_stage_completed(doc_id, stage):
                unprocessed.append((doc_id, file_hash, file_path))
                continue

        return unprocessed

    def mark_document_removed(self, document_id: str) -> None:
        """Mark a document as removed from source.

        Args:
            document_id: Document identifier
        """
        doc = self.documents.get(document_id)
        if doc:
            doc.current_version.index_status = IndexStatus.DELETED

    def get_documents_by_stage_status(
        self,
        stage: str,
        status: StageStatus,
    ) -> list[DocumentState]:
        """Get documents with a specific stage status.

        Args:
            stage: Stage name
            status: Stage status to filter by

        Returns:
            List of matching document states
        """
        result = []
        for doc in self.documents.values():
            stage_info = doc.current_version.stages.get(stage)
            if (
                stage_info
                and stage_info.status == status
                or status == StageStatus.NOT_STARTED
                and stage not in doc.current_version.stages
            ):
                result.append(doc)

        return result

    def get_documents_by_index_status(
        self,
        status: IndexStatus,
    ) -> list[DocumentState]:
        """Get documents with a specific index status.

        Args:
            status: Index status to filter by

        Returns:
            List of matching document states
        """
        return [
            doc for doc in self.documents.values() if doc.current_version.index_status == status
        ]

    def _compute_summary(self) -> dict:
        """Compute summary statistics."""
        by_stage: dict[str, int] = {}
        by_index_status: dict[str, int] = {}

        for doc in self.documents.values():
            # Count by current stage
            current_stage = doc.current_version.current_stage or "not_started"
            by_stage[current_stage] = by_stage.get(current_stage, 0) + 1

            # Count by index status
            index_status = doc.current_version.index_status.value
            by_index_status[index_status] = by_index_status.get(index_status, 0) + 1

        return {
            "total_documents": len(self.documents),
            "by_stage": by_stage,
            "by_index_status": by_index_status,
            "last_updated": self.last_updated,
        }

    def _serialize_document(self, doc: DocumentState) -> dict:
        """Serialize document to dict."""
        return {
            "document_id": doc.document_id,
            "dataset_name": doc.dataset_name,
            "relative_path": doc.relative_path,
            "current_version": self._serialize_version(doc.current_version),
            "version_history": [self._serialize_version(v) for v in doc.version_history],
        }

    def _serialize_version(self, version: DocumentVersion) -> dict:
        """Serialize document version to dict."""
        return {
            "file_hash": version.file_hash,
            "discovered_at": version.discovered_at,
            "file_size_bytes": version.file_size_bytes,
            "stages": {
                name: self._serialize_stage(stage) for name, stage in version.stages.items()
            },
            "current_stage": version.current_stage,
            "index_status": version.index_status.value,
        }

    def _serialize_stage(self, stage: StageInfo) -> dict:
        """Serialize stage info to dict."""
        data = {
            "status": stage.status.value,
            "started_at": stage.started_at,
            "completed_at": stage.completed_at,
            "failed_at": stage.failed_at,
        }

        if stage.error:
            data["error"] = asdict(stage.error)

        if stage.output:
            data["output"] = asdict(stage.output)

        if stage.metadata:
            data["metadata"] = stage.metadata

        return data

    def _deserialize_document(self, data: dict) -> DocumentState:
        """Deserialize document from dict."""
        return DocumentState(
            document_id=data["document_id"],
            dataset_name=data["dataset_name"],
            relative_path=data["relative_path"],
            current_version=self._deserialize_version(data["current_version"]),
            version_history=[self._deserialize_version(v) for v in data.get("version_history", [])],
        )

    def _deserialize_version(self, data: dict) -> DocumentVersion:
        """Deserialize document version from dict."""
        return DocumentVersion(
            file_hash=data["file_hash"],
            discovered_at=data["discovered_at"],
            file_size_bytes=data["file_size_bytes"],
            stages={name: self._deserialize_stage(s) for name, s in data.get("stages", {}).items()},
            current_stage=data.get("current_stage"),
            index_status=IndexStatus(data.get("index_status", "pending")),
        )

    def _deserialize_stage(self, data: dict) -> StageInfo:
        """Deserialize stage info from dict."""
        error = None
        if "error" in data:
            error_data = data["error"]
            error = ErrorInfo(
                type=error_data["type"],
                message=error_data["message"],
                classification=ErrorClassification(error_data["classification"]),
                traceback=error_data.get("traceback"),
                retry_count=error_data.get("retry_count", 0),
                max_retries=error_data.get("max_retries", 3),
                last_retry_at=error_data.get("last_retry_at"),
                retry_after=error_data.get("retry_after"),
            )

        output = None
        if "output" in data:
            output = StageOutput(**data["output"])

        return StageInfo(
            status=StageStatus(data["status"]),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            failed_at=data.get("failed_at"),
            error=error,
            output=output,
            metadata=data.get("metadata"),
        )
