"""Client for tracking which files have been embedded.

DEPRECATED: This module is deprecated as of Phase 2 refactoring.
Embedding state tracking has been consolidated into PipelineManifest.
Use PipelineManifest.is_stage_completed(document_id, "embedding") instead.

This module is kept for backward compatibility with existing tests only.
It will be removed in a future version.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

from lovdata_pipeline.domain.models import FileMetadata
from lovdata_pipeline.utils.file_ops import atomic_write_json
from lovdata_pipeline.utils.path_utils import parse_lovdata_path_legacy


class EmbeddedFileClient:
    """Client for tracking embedded file state.

    DEPRECATED: Use PipelineManifest for state tracking instead.

    Similar to LovligClient's processing state tracking, but specifically
    for embeddings. Tracks which files have been embedded and when.

    Args:
        embedded_state_file: Path to embedded_files.json state file
        lovlig_state_file: Path to lovlig's state.json for hash lookups
    """

    def __init__(self, embedded_state_file: Path, lovlig_state_file: Path):
        """Initialize the embedded file client."""
        self.embedded_state_file = embedded_state_file
        self.lovlig_state_file = lovlig_state_file

    def read_embedded_state(self) -> dict[str, dict[str, dict]]:
        """Read the embedded files state file.

        Returns:
            Dictionary mapping dataset_name -> {file_path: embedded_info}
            where embedded_info contains: file_hash, embedded_at, chunk_count, model_name
        """
        if not self.embedded_state_file.exists():
            return {}

        try:
            with open(self.embedded_state_file) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def write_embedded_state(self, state: dict[str, dict[str, dict]]) -> None:
        """Write embedded state atomically.

        Args:
            state: Dictionary mapping dataset_name -> {file_path: embedded_info}
        """
        atomic_write_json(self.embedded_state_file, state)

    def read_lovlig_state(self) -> dict:
        """Read lovlig's state.json file for file hashes.

        Returns:
            Lovlig state dictionary

        Raises:
            FileNotFoundError: If state file doesn't exist
        """
        if not self.lovlig_state_file.exists():
            raise FileNotFoundError(f"Lovlig state file not found: {self.lovlig_state_file}")

        with open(self.lovlig_state_file) as f:
            return json.load(f)

    def get_files_needing_embedding(
        self, changed_file_paths: list[str], force_reembed: bool = False
    ) -> list[FileMetadata]:
        """Get files that need embedding.

        Returns files where:
        - File hash changed since last embedding OR
        - File never been embedded OR
        - force_reembed=True

        Args:
            changed_file_paths: List of file paths that have changed (from changed_file_paths asset)
            force_reembed: If True, return all changed files regardless of embedded state

        Returns:
            List of FileMetadata objects for files needing embedding
        """
        if force_reembed:
            # Return all files - they need re-embedding
            return self._convert_paths_to_metadata(changed_file_paths)

        embedded_state = self.read_embedded_state()
        lovlig_state = self.read_lovlig_state()

        files_to_embed = []

        for file_path in changed_file_paths:
            # Extract dataset and relative path from absolute path
            file_path_obj = Path(file_path)

            # Parse path using utility function
            dataset_name, relative_path = parse_lovdata_path_legacy(file_path_obj)

            if not dataset_name or not relative_path:
                # Can't parse path, include file to be safe
                files_to_embed.append(self._create_file_metadata(file_path, None, None))
                continue

            try:
                dataset_state = lovlig_state.get("raw_datasets", {}).get(dataset_name, {})
                file_state = dataset_state.get("files", {}).get(relative_path, {})
                current_hash = file_state.get("sha256")

                if not current_hash:
                    # Can't find hash, include file to be safe
                    files_to_embed.append(
                        self._create_file_metadata(file_path, dataset_name, relative_path)
                    )
                    continue

                # Get embedded hash
                embedded_info = embedded_state.get(dataset_name, {}).get(relative_path, {})
                embedded_hash = embedded_info.get("file_hash")

                # Need embedding if hash changed or never embedded
                if current_hash != embedded_hash:
                    files_to_embed.append(
                        self._create_file_metadata(file_path, dataset_name, relative_path)
                    )

            except (ValueError, IndexError):
                # Error parsing path, include to be safe
                files_to_embed.append(self._create_file_metadata(file_path, None, None))

        return files_to_embed

    def _convert_paths_to_metadata(self, file_paths: list[str]) -> list[FileMetadata]:
        """Convert file paths to FileMetadata objects.

        Args:
            file_paths: List of absolute file paths

        Returns:
            List of FileMetadata objects
        """
        return [self._create_file_metadata(fp, None, None) for fp in file_paths]

    def _create_file_metadata(
        self, file_path: str, dataset_name: str | None, relative_path: str | None
    ) -> FileMetadata:
        """Create FileMetadata from file path.

        Args:
            file_path: Absolute file path
            dataset_name: Dataset name (if known)
            relative_path: Relative path within dataset (if known)

        Returns:
            FileMetadata object
        """
        file_path_obj = Path(file_path)

        # Try to extract document_id from filename
        document_id = file_path_obj.stem

        # Get file size
        file_size = file_path_obj.stat().st_size if file_path_obj.exists() else 0

        return FileMetadata(
            relative_path=relative_path or str(file_path_obj),
            absolute_path=file_path_obj,
            file_hash="",  # Not needed for embedding
            dataset_name=dataset_name or "unknown",
            status="added",  # Not used for embedding
            file_size_bytes=file_size,
            document_id=document_id,
        )

    def mark_file_embedded(
        self,
        dataset_name: str,
        file_path: str,
        file_hash: str,
        chunk_count: int,
        model_name: str,
        embedded_at: str | None = None,
    ) -> None:
        """Mark a file as successfully embedded.

        Updates embedded_files.json with embedding metadata.

        Args:
            dataset_name: Dataset name (e.g., 'gjeldende-lover.tar.bz2')
            file_path: Relative file path within dataset
            file_hash: SHA256 hash of file contents
            chunk_count: Number of chunks embedded
            model_name: Name of embedding model used
            embedded_at: Optional ISO timestamp (defaults to now)
        """
        embedded_state = self.read_embedded_state()

        # Ensure dataset entry exists
        if dataset_name not in embedded_state:
            embedded_state[dataset_name] = {}

        # Set embedded metadata
        timestamp = embedded_at or datetime.now(UTC).isoformat()
        embedded_state[dataset_name][file_path] = {
            "file_hash": file_hash,
            "embedded_at": timestamp,
            "chunk_count": chunk_count,
            "model_name": model_name,
        }

        # Write back atomically
        self.write_embedded_state(embedded_state)

    def clean_removed_files(self, lovlig_state: dict | None = None) -> int:
        """Remove entries for files that no longer exist in lovlig's state.

        Args:
            lovlig_state: Optional pre-loaded lovlig state (for efficiency)

        Returns:
            Number of entries removed from embedded state
        """
        embedded_state = self.read_embedded_state()

        if lovlig_state is None:
            try:
                lovlig_state = self.read_lovlig_state()
            except FileNotFoundError:
                return 0

        removed_count = 0
        datasets_to_remove = []

        for dataset_name, embedded_files in embedded_state.items():
            # Get current files in this dataset from lovlig
            dataset_files = (
                lovlig_state.get("raw_datasets", {}).get(dataset_name, {}).get("files", {})
            )

            # Find files in embedded state that are removed or no longer exist
            files_to_remove = []
            for file_path in list(embedded_files.keys()):
                file_state = dataset_files.get(file_path, {})
                status = file_state.get("status")

                # Remove if file doesn't exist in lovlig or has status='removed'
                if not file_state or status == "removed":
                    files_to_remove.append(file_path)

            # Remove the files
            for file_path in files_to_remove:
                del embedded_files[file_path]
                removed_count += 1

            # If dataset now has no embedded files, mark for removal
            if not embedded_files:
                datasets_to_remove.append(dataset_name)

        # Remove empty dataset entries
        for dataset_name in datasets_to_remove:
            del embedded_state[dataset_name]

        # Write back if we made changes
        if removed_count > 0:
            self.write_embedded_state(embedded_state)

        return removed_count
