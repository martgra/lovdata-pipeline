"""Ingestion assets for syncing Lovdata datasets.

These assets orchestrate the lovlig library to:
1. Sync datasets from Lovdata
2. Detect changed files
3. Detect removed files

All assets are thin - they delegate to domain/infrastructure layers.
"""

import dagster as dg

from lovdata_pipeline.config.settings import get_settings
from lovdata_pipeline.domain.models import FileMetadata, RemovalInfo
from lovdata_pipeline.resources.lovlig import LovligResource


@dg.asset(
    group_name="ingestion",
    compute_kind="lovlig",
    description="Sync Lovdata datasets using lovlig library",
)
def lovdata_sync(context: dg.AssetExecutionContext, lovlig: LovligResource) -> dg.MaterializeResult:
    """Sync Lovdata datasets using lovlig.

    This asset:
    1. Calls lovlig to download/extract datasets
    2. Updates state.json with file hashes
    3. Returns statistics about changes

    Returns MaterializeResult with metadata (not actual files).

    Args:
        context: Dagster execution context
        lovlig: Lovlig resource for dataset operations

    Returns:
        MaterializeResult with sync statistics metadata
    """
    context.log.info("Starting Lovdata dataset sync")

    try:
        # Execute lovlig sync (this downloads, extracts, updates state)
        stats = lovlig.sync_datasets(force_download=False)

        context.log.info(
            f"Sync complete: {stats.files_added} added, "
            f"{stats.files_modified} modified, {stats.files_removed} removed"
        )

        # Clean up processing state for removed files
        removed_count = lovlig.clean_removed_files_from_processed_state()
        if removed_count > 0:
            context.log.info(f"Cleaned {removed_count} removed files from processing state")

        # Return metadata (not files!)
        return dg.MaterializeResult(
            metadata={
                "files_added": dg.MetadataValue.int(stats.files_added),
                "files_modified": dg.MetadataValue.int(stats.files_modified),
                "files_removed": dg.MetadataValue.int(stats.files_removed),
                "total_changed": dg.MetadataValue.int(stats.total_changed),
                "duration_seconds": dg.MetadataValue.float(stats.duration_seconds),
            }
        )

    except FileNotFoundError as e:
        context.log.error(f"State file not found: {e}")
        context.log.info("This might be first run - sync will download all datasets")
        raise
    except Exception as e:
        context.log.error(f"Sync failed: {e}")
        raise


@dg.asset(
    group_name="ingestion",
    compute_kind="lovlig",
    deps=[lovdata_sync],
    description="Get list of changed file paths for processing",
)
def changed_file_paths(context: dg.AssetExecutionContext, lovlig: LovligResource) -> list[str]:
    """Get list of XML file paths that need processing.

    Returns only files that:
    1. Have been added or modified by lovlig (status='added' or 'modified')
    2. AND have not been successfully processed yet (no processed_at or outdated)

    Use LOVDATA_FORCE_REPROCESS=true to bypass processed_at filtering and
    reprocess all changed files (useful after schema changes or for reindexing).

    CRITICAL: This asset returns PATHS, not file contents!
    Downstream assets will load files one-by-one.

    Args:
        context: Dagster execution context
        lovlig: Lovlig resource for querying state

    Returns:
        List of absolute file paths as strings
    """
    settings = get_settings()

    context.log.info(
        f"Querying lovlig state for unprocessed files (force_reprocess={settings.force_reprocess})"
    )

    # Get file metadata from lovlig (not contents!)
    # This filters to only unprocessed files unless force_reprocess=True
    unprocessed_files: list[FileMetadata] = lovlig.get_unprocessed_files(
        force_reprocess=settings.force_reprocess
    )

    # Convert to paths
    file_paths = [str(f.absolute_path) for f in unprocessed_files]

    if not file_paths:
        context.log.info("No unprocessed files found")
        return []

    # Calculate total size
    total_size_mb = sum(f.file_size_bytes for f in unprocessed_files) / (1024 * 1024)

    context.log.info(f"Found {len(file_paths)} unprocessed files ({total_size_mb:.2f} MB)")

    # Log metadata to Dagster UI
    context.add_output_metadata(
        {
            "file_count": dg.MetadataValue.int(len(file_paths)),
            "added_count": dg.MetadataValue.int(
                sum(1 for f in unprocessed_files if f.status == "added")
            ),
            "modified_count": dg.MetadataValue.int(
                sum(1 for f in unprocessed_files if f.status == "modified")
            ),
            "total_size_mb": dg.MetadataValue.float(total_size_mb),
            "force_reprocess": dg.MetadataValue.bool(settings.force_reprocess),
            "sample_files": dg.MetadataValue.text(
                "\n".join(str(f.relative_path) for f in unprocessed_files[:5])
            ),
        }
    )

    # Return list of paths (strings fit in memory!)
    return file_paths


@dg.asset(
    group_name="ingestion",
    compute_kind="lovlig",
    deps=[lovdata_sync],
    description="Get metadata about removed files for cleanup",
)
def removed_file_metadata(context: dg.AssetExecutionContext, lovlig: LovligResource) -> list[dict]:
    """Get metadata about files removed from Lovdata.

    Returns list of dicts with document IDs and metadata
    (NOT file contents - files are already deleted!)

    Args:
        context: Dagster execution context
        lovlig: Lovlig resource for querying state

    Returns:
        List of removal info dicts
    """
    context.log.info("Querying lovlig state for removed files")

    removed_files: list[RemovalInfo] = lovlig.get_removed_files()

    if not removed_files:
        context.log.info("No removed files found")
        return []

    # Convert to dicts for serialization using Pydantic's model_dump
    removal_info = [f.model_dump() for f in removed_files]

    context.log.info(f"Found {len(removal_info)} removed files")

    # Log metadata
    context.add_output_metadata(
        {
            "removed_count": dg.MetadataValue.int(len(removal_info)),
            "document_ids": dg.MetadataValue.text(
                "\n".join(r["document_id"] for r in removal_info[:10])
            ),
        }
    )

    return removal_info
