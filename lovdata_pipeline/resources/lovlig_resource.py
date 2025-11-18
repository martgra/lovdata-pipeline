"""Dagster resource wrapper for the lovlig library.

This module provides integration between Dagster and the lovlig library
for syncing Lovdata datasets and querying change state.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from dagster import ConfigurableResource

if TYPE_CHECKING:
    try:
        from lovdata_processing import (
            FileQueryService,
            StateManager,
            sync_datasets,
        )
        from lovdata_processing import (
            Settings as LovligSettings,
        )
    except ImportError:
        pass


class LovligResource(ConfigurableResource):
    """Dagster resource wrapper for lovlig library.

    This resource provides methods to sync Lovdata datasets using the lovlig
    library and query the state.json manifest for changed files.

    Attributes:
        dataset_filter: Filter for which datasets to sync (e.g., "gjeldende")
        raw_data_dir: Directory for downloaded ZIP files
        extracted_data_dir: Directory for extracted XML files
        state_file: Path to state.json manifest file
        max_download_concurrency: Maximum concurrent downloads
    """

    dataset_filter: str = "gjeldende"
    raw_data_dir: str = "./data/raw"
    extracted_data_dir: str = "./data/extracted"
    state_file: str = "./data/state.json"
    max_download_concurrency: int = 4

    def get_settings(self):
        """Get lovlig settings configuration.

        Returns:
            LovligSettings object configured with resource parameters
        """
        from lovdata_processing import Settings as LovligSettings

        return LovligSettings(
            dataset_filter=self.dataset_filter,
            raw_data_dir=Path(self.raw_data_dir),
            extracted_data_dir=Path(self.extracted_data_dir),
            state_file=Path(self.state_file),
            max_download_concurrency=self.max_download_concurrency,
        )

    def sync_datasets(self, force_download: bool = False):
        """Sync Lovdata datasets using lovlig.

        This downloads, extracts, and tracks changes in legal documents.

        Args:
            force_download: Force re-download of all files even if unchanged
        """
        from lovdata_processing import sync_datasets

        config = self.get_settings()
        sync_datasets(config=config, force_download=force_download)

    def get_changed_files(self, status: str = "added") -> list[dict]:
        """Get files by status from lovlig state.

        Args:
            status: File status to filter by ('added', 'modified', 'removed')

        Returns:
            List of file metadata dictionaries matching the status
        """
        from lovdata_processing import StateManager

        config = self.get_settings()

        changed_files = []
        with StateManager(config.state_file) as state:
            # Iterate through all datasets
            for dataset_name, dataset_info in state.data.raw_datasets.items():
                # Iterate through all files in this dataset
                for file_path, file_info in dataset_info.files.items():
                    if file_info.status == status:
                        changed_files.append(
                            {
                                "path": file_info.path,
                                "size": file_info.size,
                                "status": file_info.status,
                                "dataset": dataset_name,
                            }
                        )

        return changed_files

    def get_all_changed_files(self) -> dict[str, list[dict]]:
        """Get all changed files grouped by status.

        Returns:
            Dictionary mapping status ('added', 'modified', 'removed')
            to lists of file metadata
        """
        return {
            "added": self.get_changed_files("added"),
            "modified": self.get_changed_files("modified"),
            "removed": self.get_changed_files("removed"),
        }

    def get_file_path(self, file_meta: dict) -> Path:
        """Get full path to extracted XML file.

        Args:
            file_meta: File metadata dictionary from lovlig state

        Returns:
            Full path to the extracted XML file
        """
        config = self.get_settings()
        # The extracted path needs the dataset name without the .tar.bz2 extension
        dataset_name = file_meta["dataset"].replace(".tar.bz2", "")
        return config.extracted_data_dir / dataset_name / file_meta["path"]
