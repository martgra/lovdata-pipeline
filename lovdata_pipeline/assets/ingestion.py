"""Ingestion assets for syncing and parsing Lovdata documents.

This module contains Dagster assets for:
- Syncing Lovdata datasets using the lovlig library
- Detecting changed files
- Parsing XML documents into structured chunks
"""

from __future__ import annotations

from typing import Iterator

from dagster import asset

from lovdata_pipeline.configs import IngestionConfig, ParsingConfig
from lovdata_pipeline.parsers import LegalChunk, LovdataXMLParser
from lovdata_pipeline.resources import LovligResource


@asset(group_name="ingestion", compute_kind="lovlig")
def lovdata_sync(context, lovlig: LovligResource) -> dict[str, int]:  # pylint: disable=redefined-outer-name
    """Sync Lovdata datasets using lovlig library.

    This asset uses the lovlig library to download, extract, and track
    changes in Lovdata legal documents. It replaces manual file inventory
    and download logic.

    Args:
        context: Dagster execution context
        lovlig: LovligResource for syncing datasets

    Returns:
        Dictionary with counts of added, modified, and removed files
    """
    context.log.info("Starting Lovdata sync with lovlig")

    # Let lovlig handle downloading, extracting, and change detection
    lovlig.sync_datasets(force_download=False)

    # Get statistics on what changed
    changed = lovlig.get_all_changed_files()

    stats = {
        "added": len(changed["added"]),
        "modified": len(changed["modified"]),
        "removed": len(changed["removed"]),
    }

    context.log.info(f"Sync complete: {stats}")
    context.add_output_metadata(stats)

    return stats


@asset(group_name="ingestion", compute_kind="lovlig")
def changed_legal_documents(  # pylint: disable=redefined-outer-name
    context,
    config: IngestionConfig,
    lovlig: LovligResource,
    lovdata_sync: dict[str, int],  # Depends on sync completing
) -> dict:
    """Get metadata about files that need processing (added or modified).

    This asset queries the lovlig state to identify files that have been
    added or modified since the last sync. Returns metadata directly -
    Dagster handles serialization via IO Manager.

    Args:
        context: Dagster execution context
        config: Ingestion configuration (max_files, file_batch_size)
        lovlig: LovligResource for querying state
        lovdata_sync: Dependency on sync completion

    Returns:
        Dictionary with file metadata and processing configuration
    """
    max_files = config.max_files
    batch_size = config.file_batch_size

    # Get changed files from lovlig state
    added = lovlig.get_changed_files("added")
    modified = lovlig.get_changed_files("modified")

    all_file_meta = added + modified
    total_available = len(all_file_meta)

    # Apply file limit if set
    if max_files > 0:
        context.log.info(
            f"Limiting to first {max_files} files (out of {total_available} available)"
        )
        all_file_meta = all_file_meta[:max_files]
        files_to_process = max_files
    else:
        files_to_process = total_available

    context.log.info(f"Will process {files_to_process} files in batches of {batch_size}")

    context.add_output_metadata(
        {
            "files_to_process": files_to_process,
            "total_files_available": total_available,
            "added_files": len(added),
            "modified_files": len(modified),
            "batch_size": batch_size,
            "num_batches": (files_to_process + batch_size - 1) // batch_size,
        }
    )

    # Return metadata directly - IO Manager handles storage
    return {
        "file_metadata": all_file_meta,
        "batch_size": batch_size,
        "total_files": files_to_process,
    }


@asset(group_name="ingestion", compute_kind="xml_parsing", io_manager_key="chunks_io_manager")
def parsed_legal_chunks(
    context,
    config: ParsingConfig,
    changed_legal_documents: dict,
    lovlig: LovligResource,
) -> Iterator[list[LegalChunk]]:
    """Parse XML files from lovlig and extract chunks with token-aware splitting.

    This asset processes files in streaming batches to avoid memory issues.
    Yields batches of chunks that are handled by the ChunksIOManager for
    memory-efficient storage.

    Token-aware splitting strategy:
    1. Parse at legalArticle level
    2. If article exceeds max_tokens:
       a. Try splitting at legalP (paragraph) boundaries (preserves XML structure)
       b. Fall back to text-based splitting if needed
    3. Preserve all XML metadata across splits

    Args:
        context: Dagster execution context
        config: Parsing configuration (max_tokens, overlap_tokens)
        changed_legal_documents: Metadata dict from upstream asset
        lovlig: LovligResource for resolving file paths

    Yields:
        Batches of LegalChunk objects
    """
    # Get metadata directly from upstream asset (no file I/O)
    file_metadata_list = changed_legal_documents["file_metadata"]
    batch_size = changed_legal_documents["batch_size"]
    total_files = changed_legal_documents["total_files"]

    if not file_metadata_list:
        context.log.info("No documents to parse")
        return

    # Get token-aware parsing configuration
    max_tokens = config.max_tokens
    overlap_tokens = config.overlap_tokens

    parser = LovdataXMLParser(
        chunk_level="legalArticle", max_tokens=max_tokens, overlap_tokens=overlap_tokens
    )

    total_chunks = 0
    split_count = 0
    files_processed = 0

    context.log.info(
        f"Starting to parse {total_files} documents in batches of {batch_size} "
        f"(max_tokens={max_tokens}, overlap={overlap_tokens})"
    )

    # Process files in batches and yield chunks (IO Manager handles storage)
    for batch_start in range(0, len(file_metadata_list), batch_size):
        batch_end = min(batch_start + batch_size, len(file_metadata_list))
        batch = file_metadata_list[batch_start:batch_end]

        context.log.info(
            f"Processing batch {batch_start // batch_size + 1}: "
            f"files {batch_start + 1}-{batch_end} of {total_files}"
        )

        batch_chunks = []
        for file_meta in batch:
            try:
                file_path = lovlig.get_file_path(file_meta)
                if not file_path.exists():
                    context.log.warning(f"File not found: {file_path}")
                    continue

                chunks = parser.parse_document(file_path)
                batch_chunks.extend(chunks)
                files_processed += 1

                # Track splits
                split_count += sum(1 for c in chunks if c.is_split)

            except Exception as e:
                context.log.error(f"Failed to parse {file_meta}: {e}")
                continue

        if batch_chunks:
            total_chunks += len(batch_chunks)

            # Log progress after each batch
            context.log.info(
                f"Batch complete: {files_processed}/{total_files} files processed, "
                f"{total_chunks} total chunks generated"
            )

            # Yield batch for IO Manager to handle
            yield batch_chunks

    context.log.info(
        f"Parsed {total_chunks} chunks from {files_processed} files "
        f"({split_count} chunks were split)"
    )

    context.add_output_metadata(
        {
            "total_chunks": total_chunks,
            "files_processed": files_processed,
            "chunks_split": split_count,
            "avg_chunks_per_file": (
                round(total_chunks / files_processed, 2) if files_processed > 0 else 0
            ),
        }
    )
