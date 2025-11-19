"""Dagster resource for lovlig.

This resource makes the lovlig infrastructure client available to Dagster assets.
"""

from pathlib import Path

from dagster import ConfigurableResource

from lovdata_pipeline.domain.models import FileMetadata, RemovalInfo, SyncStatistics
from lovdata_pipeline.infrastructure.lovlig_client import LovligClient


class LovligResource(ConfigurableResource):
    """Dagster resource for interacting with lovlig.

    This resource provides methods to:
    - Sync datasets from Lovdata
    - Query changed files from state
    - Get file metadata without loading file contents

    Configuration:
        dataset_filter: Filter for datasets to sync (default: 'gjeldende')
        raw_data_dir: Directory for raw archives (default: './data/raw')
        extracted_data_dir: Directory for extracted XML (default: './data/extracted')
        state_file: Path to state.json (default: './data/state.json')
        max_download_concurrency: Max concurrent downloads (default: 4)
    """

    dataset_filter: str = "gjeldende"
    raw_data_dir: str = "./data/raw"
    extracted_data_dir: str = "./data/extracted"
    state_file: str = "./data/state.json"
    max_download_concurrency: int = 4

    def _get_client(self) -> LovligClient:
        """Create a lovlig client with current configuration.

        Returns:
            Configured LovligClient instance
        """
        return LovligClient(
            dataset_filter=self.dataset_filter,
            raw_data_dir=Path(self.raw_data_dir),
            extracted_data_dir=Path(self.extracted_data_dir),
            state_file=Path(self.state_file),
            max_download_concurrency=self.max_download_concurrency,
        )

    def sync_datasets(self, force_download: bool = False) -> SyncStatistics:
        """Execute lovlig's dataset sync.

        Downloads, extracts, and updates state.json.

        Args:
            force_download: If True, re-download all datasets

        Returns:
            SyncStatistics with counts and duration

        Raises:
            Exception: If sync fails
        """
        client = self._get_client()
        return client.sync_datasets(force_download=force_download)

    def get_statistics(self) -> SyncStatistics:
        """Get statistics about changed files.

        Returns:
            SyncStatistics with file counts
        """
        client = self._get_client()
        return client.get_statistics()

    def get_changed_files(self) -> list[FileMetadata]:
        """Get metadata for all added and modified files.

        Returns:
            List of FileMetadata objects
        """
        client = self._get_client()
        return client.get_changed_files()

    def get_removed_files(self) -> list[RemovalInfo]:
        """Get metadata for all removed files.

        Returns:
            List of RemovalInfo objects
        """
        client = self._get_client()
        return client.get_removed_files()

    def get_unprocessed_files(self, force_reprocess: bool = False) -> list[FileMetadata]:
        """Get files that have changed and need processing.

        Returns files where status is 'added' or 'modified' AND either:
        - File has never been processed (no processed_at field)
        - File changed after it was last processed (last_changed > processed_at)
        - force_reprocess=True (ignore processed_at entirely)

        Args:
            force_reprocess: If True, return all changed files regardless of processed_at

        Returns:
            List of FileMetadata objects for files needing processing
        """
        client = self._get_client()
        return client.get_unprocessed_files(force_reprocess=force_reprocess)

    def mark_file_processed(self, dataset_name: str, file_path: str) -> None:
        """Mark a file as successfully processed.

        Updates state.json with current timestamp in processed_at field.

        Args:
            dataset_name: Dataset name (e.g., 'gjeldende-lover.tar.bz2')
            file_path: Relative file path within dataset

        Raises:
            FileNotFoundError: If state file doesn't exist
            KeyError: If dataset or file not found in state
        """
        client = self._get_client()
        client.mark_file_processed(dataset_name, file_path)

    def clean_removed_files_from_processed_state(self) -> int:
        """Remove entries for removed files from processing state.

        Returns:
            Number of entries removed
        """
        client = self._get_client()
        return client.clean_removed_files_from_processed_state()
