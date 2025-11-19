"""Client wrapper for lovlig library.

This module wraps the lovlig library and provides a clean interface
for interacting with Lovdata datasets without exposing implementation details.

Processing State:
    The client maintains a separate processed_files.json to track which files
    have been successfully processed. This is independent of lovlig's state.json
    because lovlig regenerates its state on every sync, which would wipe out
    any custom fields we add.
"""

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lovdata_processing import Settings as LovligSettings
from lovdata_processing import sync_datasets

from lovdata_pipeline.domain.models import FileMetadata, RemovalInfo, SyncStatistics


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
    """

    def __init__(
        self,
        dataset_filter: str,
        raw_data_dir: Path,
        extracted_data_dir: Path,
        state_file: Path,
        max_download_concurrency: int = 4,
    ):
        """Initialize the lovlig client."""
        self.dataset_filter = dataset_filter
        self.raw_data_dir = raw_data_dir
        self.extracted_data_dir = extracted_data_dir
        self.state_file = state_file
        self.max_download_concurrency = max_download_concurrency
        # Separate file for tracking processing state (independent of lovlig)
        self.processed_state_file = state_file.parent / "processed_files.json"

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

    def read_processed_state(self) -> dict[str, dict[str, str]]:
        """Read the processing state file.

        Returns:
            Dictionary mapping dataset_name -> {file_path: processed_at_timestamp}
        """
        if not self.processed_state_file.exists():
            return {}

        try:
            with open(self.processed_state_file) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def write_processed_state(self, state: dict[str, dict[str, str]]) -> None:
        """Write processing state atomically.

        Args:
            state: Dictionary mapping dataset_name -> {file_path: processed_at_timestamp}
        """
        # Ensure parent directory exists
        self.processed_state_file.parent.mkdir(parents=True, exist_ok=True)

        # Write to temp file first
        temp_file = self.processed_state_file.with_suffix(".tmp")
        with open(temp_file, "w") as f:
            json.dump(state, f, indent=2)

        # Atomic rename
        temp_file.replace(self.processed_state_file)

    def mark_file_processed(
        self, dataset_name: str, file_path: str, processed_at: str | None = None
    ) -> None:
        """Mark a file as successfully processed.

        Updates processed_files.json (separate from lovlig's state.json).

        Args:
            dataset_name: Dataset name (e.g., 'gjeldende-lover.tar.bz2')
            file_path: Relative file path within dataset
            processed_at: Optional ISO timestamp (defaults to now)
        """
        processed_state = self.read_processed_state()

        # Ensure dataset entry exists
        if dataset_name not in processed_state:
            processed_state[dataset_name] = {}

        # Set processed_at timestamp
        timestamp = processed_at or datetime.now(UTC).isoformat()
        processed_state[dataset_name][file_path] = timestamp

        # Write back atomically
        self.write_processed_state(processed_state)

    def clean_removed_files_from_processed_state(self) -> int:
        """Remove entries for files that no longer exist in lovlig's state.

        This cleans up processed_files.json by removing tracking for files
        that have been removed from the dataset.

        Returns:
            Number of entries removed from processing state
        """
        processed_state = self.read_processed_state()
        lovlig_state = self.read_state()

        removed_count = 0
        datasets_to_remove = []

        for dataset_name, processed_files in processed_state.items():
            # Get current files in this dataset from lovlig
            dataset_files = (
                lovlig_state.get("raw_datasets", {}).get(dataset_name, {}).get("files", {})
            )

            # Find files in processed state that are removed or no longer exist in lovlig
            files_to_remove = []
            for file_path in list(processed_files.keys()):
                file_state = dataset_files.get(file_path, {})
                status = file_state.get("status")

                # Remove if file doesn't exist in lovlig or has status='removed'
                if not file_state or status == "removed":
                    files_to_remove.append(file_path)

            # Remove the files
            for file_path in files_to_remove:
                del processed_files[file_path]
                removed_count += 1

            # If dataset now has no processed files, mark for removal
            if not processed_files:
                datasets_to_remove.append(dataset_name)

        # Remove empty dataset entries
        for dataset_name in datasets_to_remove:
            del processed_state[dataset_name]

        # Write back if we made changes
        if removed_count > 0:
            self.write_processed_state(processed_state)

        return removed_count

    def get_unprocessed_files(self, force_reprocess: bool = False) -> list[FileMetadata]:
        """Get files that have changed and need processing.

        Returns files where status is 'added' or 'modified' AND either:
        - File has never been processed (not in processed_files.json)
        - File changed after it was last processed (last_changed > processed_at)
        - force_reprocess=True (ignore processed_at entirely)

        Args:
            force_reprocess: If True, return all changed files regardless of processing state

        Returns:
            List of FileMetadata objects for files needing processing
        """
        # Get all changed files from lovlig
        all_changed = self.get_changed_files()

        if force_reprocess:
            return all_changed

        # Load processing state (separate from lovlig's state)
        processed_state = self.read_processed_state()
        lovlig_state = self.read_state()
        unprocessed = []

        for file_meta in all_changed:
            # Check if file has been processed
            dataset_processed = processed_state.get(file_meta.dataset_name, {})
            processed_at_str = dataset_processed.get(file_meta.relative_path)

            if not processed_at_str:
                # Never processed
                unprocessed.append(file_meta)
                continue

            # Check if file changed after being processed
            # Get last_changed from lovlig's state
            dataset_files = (
                lovlig_state.get("raw_datasets", {})
                .get(file_meta.dataset_name, {})
                .get("files", {})
            )
            file_state = dataset_files.get(file_meta.relative_path, {})
            last_changed_str = file_state.get("last_changed")

            if last_changed_str:
                try:
                    last_changed = datetime.fromisoformat(last_changed_str)
                    processed_at = datetime.fromisoformat(processed_at_str)

                    if last_changed > processed_at:
                        # File changed after processing
                        unprocessed.append(file_meta)
                except (ValueError, TypeError):
                    # If we can't parse timestamps, include the file to be safe
                    unprocessed.append(file_meta)
            else:
                # No last_changed timestamp - include to be safe
                unprocessed.append(file_meta)

        return unprocessed
