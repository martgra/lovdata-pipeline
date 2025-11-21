"""Minimal wrapper around lovlig library.

Just the essentials: sync datasets and query file changes.
"""

import json
from pathlib import Path

from lovdata_processing import Settings as LovligSettings
from lovdata_processing import sync_datasets

from lovdata_pipeline.domain.models import (
    LovligFileInfo,
    LovligRemovedFileInfo,
    LovligSyncStats,
)


class Lovlig:
    """Minimal lovlig client."""

    def __init__(
        self,
        dataset_filter: str,
        raw_dir: Path,
        extracted_dir: Path,
        state_file: Path,
    ):
        """Initialize lovlig client."""
        self.dataset_filter = dataset_filter
        self.raw_dir = raw_dir
        self.extracted_dir = extracted_dir
        self.state_file = state_file

    def sync(self, force: bool = False) -> LovligSyncStats:
        """Sync datasets from Lovdata.

        Args:
            force: Force re-download of all datasets

        Returns:
            LovligSyncStats with counts of added, modified, and removed files

        Note:
            This syncs the raw datasets and updates lovlig's state.json.
            It does NOT update our pipeline_state.json - that happens during processing.
        """
        settings = LovligSettings(
            dataset_filter=self.dataset_filter,
            raw_data_dir=self.raw_dir,
            extracted_data_dir=self.extracted_dir,
            state_file=self.state_file,
            max_download_concurrency=4,
        )

        sync_datasets(config=settings, force_download=force)

        # Return stats from the updated state
        state = self._read_state()
        stats = {"added": 0, "modified": 0, "removed": 0}

        for dataset in state.get("raw_datasets", {}).values():
            for file_info in dataset.get("files", {}).values():
                status = file_info.get("status")
                if status in stats:
                    stats[status] += 1

        return LovligSyncStats(**stats)

    def _read_state(self) -> dict:
        """Read lovlig's state.json."""
        if not self.state_file.exists():
            return {}

        with open(self.state_file) as f:
            return json.load(f)

    def get_changed_files(self) -> list[LovligFileInfo]:
        """Get files with status 'added' or 'modified'.

        Returns:
            List of LovligFileInfo objects for changed files
        """
        state = self._read_state()
        files = []

        for dataset_name, dataset in state.get("raw_datasets", {}).items():
            dataset_dir = dataset_name.replace(".tar.bz2", "")

            for rel_path, file_info in dataset.get("files", {}).items():
                status = file_info.get("status")

                if status in ("added", "modified"):
                    abs_path = self.extracted_dir / dataset_dir / rel_path
                    doc_id = Path(rel_path).stem

                    files.append(
                        LovligFileInfo(
                            doc_id=doc_id,
                            path=abs_path,
                            hash=file_info.get("sha256", ""),
                            dataset=dataset_name,
                        )
                    )

        return files

    def get_all_files(self) -> list[LovligFileInfo]:
        """Get all files regardless of status.

        Returns:
            List of LovligFileInfo objects for all non-removed files
        """
        state = self._read_state()
        files = []

        for dataset_name, dataset in state.get("raw_datasets", {}).items():
            dataset_dir = dataset_name.replace(".tar.bz2", "")

            for rel_path, file_info in dataset.get("files", {}).items():
                # Include all files except removed ones
                status = file_info.get("status")
                if status != "removed":
                    abs_path = self.extracted_dir / dataset_dir / rel_path
                    doc_id = Path(rel_path).stem

                    files.append(
                        LovligFileInfo(
                            doc_id=doc_id,
                            path=abs_path,
                            hash=file_info.get("sha256", ""),
                            dataset=dataset_name,
                        )
                    )

        return files

    def get_removed_files(self) -> list[LovligRemovedFileInfo]:
        """Get files with status 'removed'.

        Returns:
            List of LovligRemovedFileInfo objects for removed files
        """
        state = self._read_state()
        files = []

        for dataset_name, dataset in state.get("raw_datasets", {}).items():
            for rel_path, file_info in dataset.get("files", {}).items():
                if file_info.get("status") == "removed":
                    doc_id = Path(rel_path).stem
                    files.append(LovligRemovedFileInfo(doc_id=doc_id, dataset=dataset_name))

        return files
