"""Ingestion assets for syncing and parsing Lovdata documents.

This module contains Dagster assets for:
- Syncing Lovdata datasets using the lovlig library
- Detecting changed files
- Parsing XML documents into structured chunks
"""

from __future__ import annotations

from pathlib import Path

from dagster import asset

from lovdata_pipeline.parsers import LovdataXMLParser
from lovdata_pipeline.resources import LovligResource
from lovdata_pipeline.services import FileService


@asset(group_name="ingestion", compute_kind="lovlig")
def lovdata_sync(context, lovlig: LovligResource) -> dict[str, int]:
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
def changed_legal_documents(
    context,
    lovlig: LovligResource,
    lovdata_sync: dict[str, int],  # Depends on sync completing
) -> dict:
    """Get metadata about files that need processing (added or modified).

    This asset queries the lovlig state to identify files that have been
    added or modified since the last sync. Returns metadata only to avoid
    memory issues - actual file processing happens in batches downstream.

    Environment Variables:
        MAX_FILES: Limit number of files to process (0 = all, default: 0)
        FILE_BATCH_SIZE: Process files in batches of this size (default: 100)

    Args:
        context: Dagster execution context
        lovlig: LovligResource for querying state
        lovdata_sync: Dependency on sync completion

    Returns:
        Dictionary with file metadata and processing configuration
    """
    import os

    max_files = int(os.getenv("MAX_FILES", "0"))  # 0 = no limit
    batch_size = int(os.getenv("FILE_BATCH_SIZE", "100"))

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

    # Return metadata - store file list in a temp file using FileService
    metadata_file = Path("data/temp_file_list.json")
    metadata_data = {
        "file_metadata": all_file_meta,
        "batch_size": batch_size,
        "total_files": files_to_process,
    }

    success = FileService.write_json(metadata_file, metadata_data)
    if not success:
        context.log.error("Failed to write metadata file")
        raise RuntimeError("Failed to write metadata file")

    context.log.info(f"Wrote file metadata to {metadata_file}")

    result = {
        "metadata_file": str(metadata_file),
        "total_files": files_to_process,
        "batch_size": batch_size,
    }
    context.log.info(f"Returning: {result}")
    return result


@asset(group_name="ingestion", compute_kind="xml_parsing")
def parsed_legal_chunks(context, changed_legal_documents: dict, lovlig: LovligResource) -> dict:
    """Parse XML files from lovlig and extract chunks with token-aware splitting.

    This asset processes files in streaming batches to avoid memory issues.
    Files are read from the metadata file created by changed_legal_documents,
    processed in batches, and chunks written to a temp file to avoid pickling issues.

    Token-aware splitting strategy:
    1. Parse at legalArticle level
    2. If article exceeds max_tokens:
       a. Try splitting at legalP (paragraph) boundaries (preserves XML structure)
       b. Fall back to text-based splitting if needed
    3. Preserve all XML metadata across splits

    Environment Variables:
    - PARSER_MAX_TOKENS: Max tokens per chunk (default: 6800, safe for 8K limit)
    - PARSER_OVERLAP_TOKENS: Token overlap for splits (default: 100)

    Args:
        context: Dagster execution context
        changed_legal_documents: Metadata dict with file list location
        lovlig: LovligResource for resolving file paths

    Returns:
        Dict with chunks_file path and total_chunks count
    """
    import os

    # Load file metadata from temp file using FileService
    metadata_file = Path(changed_legal_documents["metadata_file"])
    metadata = FileService.read_json(metadata_file)

    if not metadata:
        context.log.error(f"Metadata file not found or invalid: {metadata_file}")
        return {"chunks_file": "", "total_chunks": 0}

    file_metadata_list = metadata["file_metadata"]
    batch_size = metadata["batch_size"]
    total_files = metadata["total_files"]

    if not file_metadata_list:
        context.log.info("No documents to parse")
        return {"chunks_file": "", "total_chunks": 0}

    # Configure token-aware parsing
    max_tokens = int(os.getenv("PARSER_MAX_TOKENS", "6800"))  # Safe limit for 8K
    overlap_tokens = int(os.getenv("PARSER_OVERLAP_TOKENS", "100"))

    parser = LovdataXMLParser(
        chunk_level="legalArticle", max_tokens=max_tokens, overlap_tokens=overlap_tokens
    )

    # Prepare chunks file path
    chunks_file = Path("data/temp_chunks.pickle")

    total_chunks = 0
    split_count = 0
    files_processed = 0

    context.log.info(
        f"Starting to parse {total_files} documents in batches of {batch_size} "
        f"(max_tokens={max_tokens}, overlap={overlap_tokens})"
    )

    # Create generator for streaming writes (memory efficient)
    def generate_chunk_batches():
        """Generator that yields chunk batches for streaming writes."""
        nonlocal total_chunks, split_count, files_processed

        # Process files in batches
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
                    f"{total_chunks} total chunks written"
                )

                yield batch_chunks

    # Write chunks using FileService (streaming, memory-efficient)
    total_chunks_written, batches_written = FileService.write_chunks_streaming(
        chunks_file, generate_chunk_batches()
    )

    # Clean up temp metadata file using FileService
    FileService.cleanup_temp_files(metadata_file)

    context.log.info(
        f"Parsed {total_chunks_written} chunks from {files_processed} files "
        f"({split_count} chunks were split) in {batches_written} batches"
    )

    context.add_output_metadata(
        {
            "total_chunks": total_chunks_written,
            "files_processed": files_processed,
            "chunks_split": split_count,
            "batches_written": batches_written,
            "avg_chunks_per_file": (
                round(total_chunks_written / files_processed, 2) if files_processed > 0 else 0
            ),
        }
    )

    return {"chunks_file": str(chunks_file), "total_chunks": total_chunks_written}
