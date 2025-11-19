"""Chunking assets for processing legal documents.

These assets orchestrate the XML-aware chunking pipeline to extract
structured text chunks from Lovdata XML documents.
"""

from pathlib import Path

import dagster as dg

from lovdata_pipeline.config.settings import get_settings
from lovdata_pipeline.domain.parsers.xml_chunker import LovdataXMLChunker
from lovdata_pipeline.domain.splitters.recursive_splitter import XMLAwareRecursiveSplitter
from lovdata_pipeline.infrastructure.chunk_writer import ChunkWriter
from lovdata_pipeline.resources.lovlig import LovligResource


@dg.asset(
    group_name="processing",
    compute_kind="xml_parsing",
    deps=["changed_file_paths", "removed_file_metadata"],
    description="Parse and chunk legal documents using XML-aware splitting",
)
def legal_document_chunks(
    context: dg.AssetExecutionContext,
    changed_file_paths: list[str],
    removed_file_metadata: list[dict],
    lovlig: LovligResource,
) -> dg.MaterializeResult:
    """Parse XML files and extract chunks using XML-aware splitting.

    This asset:
    1. Removes chunks for deleted files (cleanup)
    2. Removes old chunks for modified files (prevents duplicates)
    3. Iterates through changed XML files one-by-one (memory-efficient)
    4. Extracts legalArticle nodes with XML structure preserved
    5. Splits articles using 3-tier strategy (paragraph → sentence → token)
    6. Streams chunks to JSONL file (one chunk per line)
    7. Marks successfully processed files to enable recovery/resume

    The chunking strategy:
    - First attempts to group legalP paragraphs
    - Falls back to sentence boundaries for large paragraphs
    - Uses hard token splitting only as last resort

    Recovery mechanism:
    - Appends chunks to existing output file (no clear/overwrite)
    - Marks files as processed after successful chunking
    - On retry, skips already-processed files automatically

    Deletion handling:
    - Automatically removes chunks for files deleted from Lovdata
    - Ensures output file stays synchronized with current dataset state

    Args:
        context: Dagster execution context
        changed_file_paths: List of XML file paths to process
        removed_file_metadata: Metadata about deleted files for chunk cleanup
        lovlig: Lovlig resource for marking files as processed

    Returns:
        MaterializeResult with chunking statistics metadata
    """
    settings = get_settings()

    if not changed_file_paths:
        context.log.info("No changed files to process")
        return dg.MaterializeResult(
            metadata={
                "files_processed": 0,
                "total_chunks": 0,
                "output_file": str(settings.chunk_output_path),
            }
        )

    context.log.info(f"Processing {len(changed_file_paths)} XML files")
    context.log.info(f"Max tokens per chunk: {settings.chunk_max_tokens}")
    context.log.info(f"Output: {settings.chunk_output_path}")

    # Ensure output directory exists
    settings.chunk_output_path.parent.mkdir(parents=True, exist_ok=True)

    # Initialize splitter
    splitter = XMLAwareRecursiveSplitter(max_tokens=settings.chunk_max_tokens)

    # Statistics
    total_chunks = 0
    files_processed = 0
    files_failed = 0
    failed_files = []
    split_distribution = {"none": 0, "paragraph": 0, "sentence": 0, "token": 0}
    oversized_articles = 0

    # Open output file in APPEND mode (preserves existing chunks on retry)
    # DO NOT CLEAR - this enables recovery from partial failures
    writer = ChunkWriter(settings.chunk_output_path)

    # First pass: Remove old chunks
    # Must be done BEFORE opening the writer to avoid file handle issues

    # Pass 1A: Remove chunks for deleted files
    chunks_removed_deleted = 0
    for removal in removed_file_metadata:
        doc_id = removal["document_id"]
        removed = writer.remove_chunks_for_document(doc_id)
        if removed > 0:
            context.log.info(f"Removed {removed} chunks for deleted file {doc_id}")
            chunks_removed_deleted += removed

    # Pass 1B: Remove chunks for modified documents
    for file_path in changed_file_paths:
        document_id = Path(file_path).stem
        removed_chunks = writer.remove_chunks_for_document(document_id)
        if removed_chunks > 0:
            context.log.info(f"Removed {removed_chunks} old chunks for {document_id}")

    # Second pass: Process files and write new chunks
    with writer:
        for file_path in changed_file_paths:
            file_name = Path(file_path).name
            document_id = Path(file_path).stem

            context.log.info(f"Processing {file_name}")

            try:
                # Parse XML and extract articles
                chunker = LovdataXMLChunker(file_path)
                articles = chunker.extract_articles()

                if not articles:
                    context.log.warning(f"No articles found in {file_name}")
                    continue

                # Process each article
                for article in articles:
                    # Split article into chunks
                    chunks = splitter.split_article(article)

                    # Track statistics
                    total_chunks += len(chunks)
                    if len(chunks) > 1:
                        oversized_articles += 1

                    # Count split reasons
                    for chunk in chunks:
                        split_distribution[chunk.split_reason] += 1

                    # Stream chunks to file immediately
                    writer.write_chunks(chunks)

                    # CRITICAL: article and chunks are now garbage collected
                    # Memory usage stays constant!

                files_processed += 1

                # Mark file as processed in state.json
                # Extract dataset name and relative path from absolute path
                try:
                    # Path structure: extracted_data_dir/dataset_name/relative_path
                    abs_path = Path(file_path)
                    relative_to_extracted = abs_path.relative_to(settings.extracted_data_dir)
                    parts = relative_to_extracted.parts
                    if len(parts) >= 2:
                        dataset_name = f"{parts[0]}.tar.bz2"  # Add extension back
                        relative_file_path = str(Path(*parts[1:]))
                        lovlig.mark_file_processed(dataset_name, relative_file_path)
                        context.log.debug(f"Marked {file_name} as processed")
                except (ValueError, IndexError) as e:
                    context.log.warning(
                        f"Could not mark {file_name} as processed: {e}. "
                        "File will be reprocessed on next run."
                    )

            except FileNotFoundError as e:
                context.log.error(f"File not found: {file_path} - {e}")
                files_failed += 1
                failed_files.append(file_path)
            except Exception as e:
                context.log.error(f"Failed to process {file_name}: {e}")
                files_failed += 1
                failed_files.append(file_path)
                # Continue processing other files
                continue

    # Get output file size
    output_size_mb = writer.get_file_size_mb()

    # Calculate statistics
    success_rate = (files_processed / len(changed_file_paths) * 100) if changed_file_paths else 0
    avg_chunks_per_file = total_chunks / files_processed if files_processed > 0 else 0

    # Calculate split percentages
    split_percentages = {}
    if total_chunks > 0:
        for reason, count in split_distribution.items():
            split_percentages[f"{reason}_pct"] = round(count / total_chunks * 100, 2)

    context.log.info(f"✓ Processed {files_processed} files successfully")
    context.log.info(f"✓ Extracted {total_chunks} chunks")
    context.log.info(f"✓ Output size: {output_size_mb:.2f} MB")
    context.log.info(f"✓ Split distribution: {split_distribution}")

    if files_failed > 0:
        context.log.warning(f"⚠ {files_failed} files failed to process")

    # Return metadata (not chunks!)
    metadata = {
        "files_processed": dg.MetadataValue.int(files_processed),
        "files_failed": dg.MetadataValue.int(files_failed),
        "files_deleted": dg.MetadataValue.int(len(removed_file_metadata)),
        "chunks_removed_for_deleted": dg.MetadataValue.int(chunks_removed_deleted),
        "total_chunks": dg.MetadataValue.int(total_chunks),
        "avg_chunks_per_file": dg.MetadataValue.float(
            round(avg_chunks_per_file, 2) if files_processed > 0 else 0.0
        ),
        "oversized_articles": dg.MetadataValue.int(oversized_articles),
        "output_file": dg.MetadataValue.path(str(settings.chunk_output_path)),
        "output_size_mb": dg.MetadataValue.float(round(output_size_mb, 2)),
        "success_rate": dg.MetadataValue.float(round(success_rate, 2)),
        "no_split_chunks": dg.MetadataValue.int(split_distribution["none"]),
        "paragraph_split_chunks": dg.MetadataValue.int(split_distribution["paragraph"]),
        "sentence_split_chunks": dg.MetadataValue.int(split_distribution["sentence"]),
        "token_split_chunks": dg.MetadataValue.int(split_distribution["token"]),
    }

    # Add split percentages
    for key, value in split_percentages.items():
        metadata[key] = dg.MetadataValue.float(value)

    # Add sample of failed files if any
    if failed_files:
        metadata["failed_files_sample"] = dg.MetadataValue.text("\n".join(failed_files[:10]))

    # Raise exception if too many failures
    if files_failed > len(changed_file_paths) * 0.5:
        raise RuntimeError(
            f"More than 50% of files failed: {files_failed}/{len(changed_file_paths)}"
        )

    return dg.MaterializeResult(metadata=metadata)
