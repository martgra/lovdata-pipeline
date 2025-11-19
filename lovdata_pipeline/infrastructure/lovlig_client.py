"""Client wrapper for lovlig library.

This module wraps the lovlig library and provides a clean interface
for interacting with Lovdata datasets without exposing implementation details.

State Management:
    Uses PipelineManifest for unified state tracking across all pipeline stages.
    No longer maintains separate processed_files.json - all state is in the manifest.
"""

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lovdata_processing import Settings as LovligSettings
from lovdata_processing import sync_datasets

from lovdata_pipeline.domain.models import FileMetadata, RemovalInfo, SyncStatistics
from lovdata_pipeline.infrastructure.pipeline_manifest import PipelineManifest


class LovligClient:
    """Client for interacting with lovlig library.

    This class wraps lovlig's functionality and provides methods for:
    - Syncing datasets from Lovdata
    - Querying file state
    - Getting file metadata

    Args:
        dataset_filter: Filter for datasets to sync (e.g., 'gjeldende')
        raw_data_dir: Directory for raw downloaded archives
        extracted_data_dir: Directory for extracted XML files
        state_file: Path to lovlig state.json file
        max_download_concurrency: Maximum concurrent downloads
        manifest: Optional PipelineManifest for unified state tracking
    """

    def __init__(
        self,
        dataset_filter: str,
        raw_data_dir: Path,
        extracted_data_dir: Path,
        state_file: Path,
        max_download_concurrency: int = 4,
        manifest: PipelineManifest | None = None,
    ):
        """Initialize the lovlig client."""
        self.dataset_filter = dataset_filter
        self.raw_data_dir = raw_data_dir
        self.extracted_data_dir = extracted_data_dir
        self.state_file = state_file
        self.max_download_concurrency = max_download_concurrency
        self.manifest = manifest

    def get_lovlig_settings(self) -> LovligSettings:
        """Create lovlig Settings object from client config.

        Returns:
            LovligSettings configured with client parameters
        """
        return LovligSettings(
            dataset_filter=self.dataset_filter,
            raw_data_dir=self.raw_data_dir,
            extracted_data_dir=self.extracted_data_dir,
            state_file=self.state_file,
            max_download_concurrency=self.max_download_concurrency,
        )

    def sync_datasets(self, force_download: bool = False) -> SyncStatistics:
        """Execute lovlig's dataset sync.

        Downloads, extracts, and updates state.json.

        Args:
            force_download: If True, re-download all datasets regardless of state

        Returns:
            SyncStatistics with counts of added/modified/removed files

        Raises:
            Exception: If sync operation fails
        """
        settings = self.get_lovlig_settings()

        start_time = time.time()
        sync_datasets(config=settings, force_download=force_download)
        duration = time.time() - start_time

        # Get statistics from state
        stats = self.get_statistics()
        stats.duration_seconds = duration

        return stats

    def read_state(self) -> dict[str, Any]:
        """Read lovlig's state.json file.

        Returns:
            State data as dictionary

        Raises:
            FileNotFoundError: If state file doesn't exist
            json.JSONDecodeError: If state file is corrupt
        """
        if not self.state_file.exists():
            raise FileNotFoundError(f"State file not found: {self.state_file}")

        with open(self.state_file) as f:
            return json.load(f)

    def get_statistics(self) -> SyncStatistics:
        """Get statistics about changed files from state.

        Returns:
            SyncStatistics with file counts
        """
        try:
            state = self.read_state()
        except FileNotFoundError:
            # First run - no state yet
            return SyncStatistics(
                files_added=0, files_modified=0, files_removed=0, duration_seconds=0.0
            )

        # Count files by status
        added = 0
        modified = 0
        removed = 0

        for dataset_state in state.get("datasets", {}).values():
            for file_state in dataset_state.get("files", {}).values():
                status = file_state.get("status")
                if status == "added":
                    added += 1
                elif status == "modified":
                    modified += 1
                elif status == "removed":
                    removed += 1

        return SyncStatistics(
            files_added=added, files_modified=modified, files_removed=removed, duration_seconds=0.0
        )

    def get_files_by_status(self, status: str) -> list[dict]:
        """Query lovlig's state for files with given status.

        Args:
            status: File status to filter by ('added', 'modified', or 'removed')

        Returns:
            List of file metadata dicts from state
        """
        try:
            state = self.read_state()
        except FileNotFoundError:
            return []

        result = []
        # State structure: raw_datasets[dataset_name].files[file_path]
        for dataset_name, dataset_state in state.get("raw_datasets", {}).items():
            for file_path, file_state in dataset_state.get("files", {}).items():
                if file_state.get("status") == status:
                    result.append(
                        {
                            "path": file_path,
                            "hash": file_state.get("sha256", ""),
                            "dataset": dataset_name,
                            "status": status,
                        }
                    )

        return result

    def get_file_metadata(self, file_info: dict) -> FileMetadata | None:
        """Convert file info from state to FileMetadata domain object.

        Args:
            file_info: File info dict from lovlig state

        Returns:
            FileMetadata object or None if file doesn't exist
        """
        relative_path = file_info["path"]
        # Dataset name includes .tar.bz2 extension, strip it for directory name
        dataset_dir = file_info["dataset"].replace(".tar.bz2", "")
        absolute_path = self.extracted_data_dir / dataset_dir / relative_path

        # Verify file exists (unless it's removed)
        if file_info["status"] != "removed" and not absolute_path.exists():
            return None

        # Get file size
        file_size = absolute_path.stat().st_size if absolute_path.exists() else 0

        # Extract document ID from filename
        document_id = Path(relative_path).stem

        return FileMetadata(
            relative_path=relative_path,
            absolute_path=absolute_path,
            file_hash=file_info["hash"],
            dataset_name=file_info["dataset"],
            status=file_info["status"],  # type: ignore
            file_size_bytes=file_size,
            document_id=document_id,
        )

    def get_changed_files(self) -> list[FileMetadata]:
        """Get metadata for all added and modified files.

        Returns:
            List of FileMetadata objects for changed files
        """
        added = self.get_files_by_status("added")
        modified = self.get_files_by_status("modified")

        result = []
        for file_info in added + modified:
            metadata = self.get_file_metadata(file_info)
            if metadata:
                result.append(metadata)

        return result

    def get_removed_files(self) -> list[RemovalInfo]:
        """Get metadata for all removed files.

        Returns:
            List of RemovalInfo objects for removed files
        """
        removed = self.get_files_by_status("removed")

        result = []
        for file_info in removed:
            result.append(
                RemovalInfo(
                    document_id=Path(file_info["path"]).stem,
                    relative_path=file_info["path"],
                    dataset_name=file_info["dataset"],
                    last_hash=file_info["hash"],
                )
            )

        return result

    def mark_file_processed(
        self,
        dataset_name: str,
        file_path: str,
        file_hash: str | None = None,
        _processed_at: str | None = None,  # Keep for backward compatibility but ignore
    ) -> None:
        """Mark a file as successfully processed in the manifest.

        Args:
            dataset_name: Dataset name (e.g., 'gjeldende-lover.tar.bz2')
            file_path: Relative file path within dataset
            file_hash: File hash for tracking (optional, will lookup if not provided)
            processed_at: Deprecated - kept for backward compatibility but ignored
        """
        if not self.manifest:
            # Legacy: Skip if no manifest provided
            return

        # Get document ID from file path
        document_id = Path(file_path).stem

        # Get file hash if not provided
        if not file_hash:
            try:
                state = self.read_state()
                dataset_files = state.get("raw_datasets", {}).get(dataset_name, {}).get("files", {})
                file_state = dataset_files.get(file_path, {})
                file_hash = file_state.get("sha256", "unknown")
            except (FileNotFoundError, KeyError):
                file_hash = "unknown"

        # Get file size
        dataset_dir = dataset_name.replace(".tar.bz2", "")
        absolute_path = self.extracted_data_dir / dataset_dir / file_path
        file_size = absolute_path.stat().st_size if absolute_path.exists() else 0

        # Ensure document exists in manifest
        self.manifest.ensure_document(
            document_id=document_id,
            dataset_name=dataset_name,
            relative_path=file_path,
            file_hash=file_hash,
            file_size_bytes=file_size,
        )

        # Mark chunking stage complete
        try:
            self.manifest.complete_stage(
                document_id=document_id,
                file_hash=file_hash,
                stage="chunking",
                output={"output_file": "legal_chunks.jsonl"},
                metadata={"processed_at": datetime.now(UTC).isoformat()},
            )
            self.manifest.save()
        except ValueError:
            # Document/hash mismatch, skip
            pass

    def clean_removed_files_from_processed_state(self) -> int:
        """Mark removed files in the manifest.

        Updates manifest to mark documents as deleted when they've been removed
        from the lovdata dataset.

        Returns:
            Number of documents marked as removed
        """
        if not self.manifest:
            return 0

        lovlig_state = self.read_state()
        removed_count = 0

        # Get all documents in manifest
        for doc_id, _doc_state in list(self.manifest.documents.items()):
            # Check if file still exists or has status="removed" in lovlig state
            found_active = False
            for _dataset_name, dataset_state in lovlig_state.get("raw_datasets", {}).items():
                for file_path, file_info in dataset_state.get("files", {}).items():
                    if Path(file_path).stem == doc_id:
                        # Check status - if removed, treat as not found
                        if file_info.get("status") != "removed":
                            found_active = True
                        break
                if found_active:
                    break

            if not found_active:
                # File removed or marked as removed, mark in manifest
                self.manifest.mark_document_removed(doc_id)
                removed_count += 1

        if removed_count > 0:
            self.manifest.save()

        return removed_count

    def get_unprocessed_files(
        self, stage: str = "chunking", force_reprocess: bool = False
    ) -> list[FileMetadata]:
        """Get files that have changed and need processing for a specific stage.

        Returns files where status is 'added' or 'modified' AND either:
        - Stage has never been completed (not in manifest)
        - File hash changed since stage was completed (new version in manifest)
        - force_reprocess=True (ignore manifest state)

        Args:
            stage: Pipeline stage to check ('chunking', 'embedding', 'indexing')
            force_reprocess: If True, return all changed files regardless of processing state

        Returns:
            List of FileMetadata objects for files needing processing
        """
        # Get all changed files from lovlig
        all_changed = self.get_changed_files()

        if force_reprocess or not self.manifest:
            return all_changed

        unprocessed = []

        for file_meta in all_changed:
            document_id = file_meta.document_id

            # Check if specified stage completed for this file
            if self.manifest.is_stage_completed(document_id, stage):
                # Verify hash matches (detect if file changed after processing)
                doc_state = self.manifest.get_document(document_id)
                if doc_state and doc_state.current_version.file_hash == file_meta.file_hash:
                    # Already processed with same hash, skip
                    continue

            # Needs processing
            unprocessed.append(file_meta)

        return unprocessed
