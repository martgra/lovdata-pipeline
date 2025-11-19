"""Minimal wrapper around lovlig library.

Just the essentials: sync datasets and query file changes.
"""

import json
from pathlib import Path

from lovdata_processing import Settings as LovligSettings
from lovdata_processing import sync_datasets


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

    def sync(self, force: bool = False) -> dict:
        """Sync datasets from Lovdata."""
        settings = LovligSettings(
            dataset_filter=self.dataset_filter,
            raw_data_dir=self.raw_dir,
            extracted_data_dir=self.extracted_dir,
            state_file=self.state_file,
            max_download_concurrency=4,
        )

        sync_datasets(config=settings, force_download=force)

        # Return stats
        state = self._read_state()
        stats = {"added": 0, "modified": 0, "removed": 0}

        for dataset in state.get("raw_datasets", {}).values():
            for file_info in dataset.get("files", {}).values():
                status = file_info.get("status")
                if status in stats:
                    stats[status] += 1

        return stats

    def _read_state(self) -> dict:
        """Read lovlig's state.json."""
        if not self.state_file.exists():
            return {}

        with open(self.state_file) as f:
            return json.load(f)

    def get_changed_files(self) -> list[dict]:
        """Get files with status 'added' or 'modified'.

        Returns list of dicts with:
            - doc_id: document identifier
            - path: absolute path to file
            - hash: file hash
            - dataset: dataset name
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
                        {
                            "doc_id": doc_id,
                            "path": abs_path,
                            "hash": file_info.get("sha256", ""),
                            "dataset": dataset_name,
                        }
                    )

        return files

    def get_removed_files(self) -> list[dict]:
        """Get files with status 'removed'.

        Returns list of dicts with:
            - doc_id: document identifier
            - dataset: dataset name
        """
        state = self._read_state()
        files = []

        for dataset_name, dataset in state.get("raw_datasets", {}).items():
            for rel_path, file_info in dataset.get("files", {}).items():
                if file_info.get("status") == "removed":
                    doc_id = Path(rel_path).stem
                    files.append({"doc_id": doc_id, "dataset": dataset_name})

        return files
