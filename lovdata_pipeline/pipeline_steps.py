"""Pipeline steps - pure Python functions without Dagster dependencies.

These functions contain the core pipeline logic for:
1. Syncing datasets from Lovdata
2. Chunking XML documents
3. Embedding chunks
4. Indexing in vector database

All functions now use PipelineContext for dependency injection, improving
testability and reducing repetitive client instantiation.
"""

import contextlib
import logging
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from lovdata_pipeline.domain.models import EnrichedChunk
from lovdata_pipeline.domain.parsers.xml_chunker import LovdataXMLChunker
from lovdata_pipeline.infrastructure.pipeline_manifest import (
    IndexStatus,
)
from lovdata_pipeline.pipeline_context import PipelineContext
from lovdata_pipeline.utils.path_utils import parse_lovdata_path

logger = logging.getLogger(__name__)

# Transient errors that warrant retry
TRANSIENT_EXCEPTIONS = (ConnectionError, TimeoutError, OSError)


def _create_context() -> PipelineContext:
    """Create pipeline context from settings.

    Returns:
        Initialized PipelineContext
    """
    return PipelineContext.from_settings()


def sync_datasets(force_download: bool = False) -> dict:
    """Sync datasets from Lovdata.

    Args:
        force_download: Force re-download of all datasets

    Returns:
        Statistics dictionary with files added/modified/removed
    """
    ctx = _create_context()
    logger.info("Starting Lovdata dataset sync")

    stats = ctx.lovlig_client.sync_datasets(force_download=force_download)

    logger.info(
        f"Sync complete: {stats.files_added} added, "
        f"{stats.files_modified} modified, {stats.files_removed} removed"
    )

    # Clean up processing state for removed files
    removed_count = ctx.lovlig_client.clean_removed_files_from_processed_state()
    if removed_count > 0:
        logger.info(f"Cleaned {removed_count} removed files from processing state")

    return {
        "files_added": stats.files_added,
        "files_modified": stats.files_modified,
        "files_removed": stats.files_removed,
        "total_changed": stats.total_changed,
        "duration_seconds": stats.duration_seconds,
    }


def get_changed_file_paths(force_reprocess: bool = False) -> list[str]:
    """Get list of XML file paths that need processing.

    Args:
        force_reprocess: If True, return all changed files regardless of processed state

    Returns:
        List of absolute file paths as strings
    """
    ctx = _create_context()
    logger.info(f"Querying state for unprocessed files (force_reprocess={force_reprocess})")

    unprocessed_files = ctx.lovlig_client.get_unprocessed_files(force_reprocess=force_reprocess)
    file_paths = [str(f.absolute_path) for f in unprocessed_files]

    if not file_paths:
        logger.info("No unprocessed files found")
        return []

    total_size_mb = sum(f.file_size_bytes for f in unprocessed_files) / (1024 * 1024)
    logger.info(f"Found {len(file_paths)} unprocessed files ({total_size_mb:.2f} MB)")

    return file_paths


def get_removed_file_metadata() -> list[dict]:
    """Get metadata about files removed from Lovdata.

    Returns:
        List of removal info dicts with document IDs
    """
    ctx = _create_context()
    logger.info("Querying state for removed files")

    removed_files = ctx.lovlig_client.get_removed_files()

    if not removed_files:
        logger.info("No removed files found")
        return []

    removal_info = [f.model_dump() for f in removed_files]
    logger.info(f"Found {len(removal_info)} removed files")

    return removal_info


def _cleanup_removed_chunks(ctx: PipelineContext, removed_file_metadata: list[dict]) -> int:
    """Remove chunks for deleted files.

    Args:
        ctx: Pipeline context
        removed_file_metadata: List of removal info for cleanup

    Returns:
        Total number of chunks removed
    """
    chunks_removed = 0
    for removal in removed_file_metadata:
        doc_id = removal["document_id"]
        removed = ctx.chunk_writer.remove_chunks_for_document(doc_id)
        if removed > 0:
            logger.info(f"Removed {removed} chunks for deleted file {doc_id}")
            chunks_removed += removed
    return chunks_removed


def _cleanup_modified_chunks(ctx: PipelineContext, changed_file_paths: list[str]) -> int:
    """Remove old chunks for modified documents.

    Args:
        ctx: Pipeline context
        changed_file_paths: List of file paths being processed

    Returns:
        Total number of chunks removed
    """
    chunks_removed = 0
    for file_path in changed_file_paths:
        document_id = Path(file_path).stem
        removed = ctx.chunk_writer.remove_chunks_for_document(document_id)
        if removed > 0:
            logger.info(f"Removed {removed} old chunks for {document_id}")
            chunks_removed += removed
    return chunks_removed


# Retry decorator using tenacity directly
_process_file_retry = retry(
    retry=retry_if_exception_type(TRANSIENT_EXCEPTIONS),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)


@_process_file_retry
def _process_single_file(
    file_path: str,
    ctx: PipelineContext,
) -> tuple[int, int, int, dict[str, int]]:
    """Process a single XML file and extract chunks.

    Args:
        file_path: Path to the file to process
        ctx: Pipeline context with all dependencies

    Returns:
        Tuple of (total_chunks, oversized_articles, files_processed, split_distribution)

    Raises:
        FileNotFoundError: If file doesn't exist (permanent error)
        ConnectionError, TimeoutError, OSError: Transient errors
        Exception: Other errors
    """
    file_name = Path(file_path).name
    abs_path = Path(file_path)

    # Parse path to get dataset_name
    parsed = parse_lovdata_path(abs_path, ctx.settings.extracted_data_dir)
    dataset_name = parsed.dataset_name if parsed else ""

    # Parse XML and extract articles
    chunker = LovdataXMLChunker(file_path)
    articles = chunker.extract_articles()

    if not articles:
        logger.warning(f"No articles found in {file_name}")
        return 0, 0, 1, {}

    # Process each article
    total_chunks = 0
    oversized_articles = 0
    split_distribution = defaultdict(int)

    for article in articles:
        chunks = ctx.splitter.split_article(article, dataset_name=dataset_name)
        total_chunks += len(chunks)
        if len(chunks) > 1:
            oversized_articles += 1

        for chunk in chunks:
            split_distribution[chunk.split_reason] += 1

        ctx.chunk_writer.write_chunks(chunks)

    # Mark file as processed
    _mark_file_processed(file_path, file_name, ctx)

    return total_chunks, oversized_articles, 1, dict(split_distribution)


def _mark_file_processed(file_path: str, file_name: str, ctx: PipelineContext) -> None:
    """Mark a file as successfully processed.

    Args:
        file_path: Absolute path to the file
        file_name: Name of the file (for logging)
        ctx: Pipeline context
    """
    try:
        abs_path = Path(file_path)
        parsed = parse_lovdata_path(abs_path, ctx.settings.extracted_data_dir)

        if parsed:
            ctx.lovlig_client.mark_file_processed(parsed.dataset_name, parsed.relative_path)
            logger.debug(f"Marked {file_name} as processed")
        else:
            logger.warning(
                f"Could not parse path for {file_name}. File will be reprocessed on next run."
            )
    except Exception as e:
        logger.warning(
            f"Could not mark {file_name} as processed: {e}. File will be reprocessed on next run."
        )


def chunk_documents(changed_file_paths: list[str], removed_file_metadata: list[dict]) -> dict:
    """Parse and chunk XML documents.

    Args:
        changed_file_paths: List of file paths to process
        removed_file_metadata: List of removal info for cleanup

    Returns:
        Statistics dictionary with processing results
    """
    ctx = _create_context()
    logger.info("Starting document chunking")

    # Track statistics
    total_chunks = 0
    files_processed = 0
    files_failed = 0
    failed_files = []
    oversized_articles = 0
    split_distribution = defaultdict(int)

    # Clean up removed and modified files
    _cleanup_removed_chunks(ctx, removed_file_metadata)
    _cleanup_modified_chunks(ctx, changed_file_paths)

    # Process files
    with ctx.chunk_writer:
        for file_path in changed_file_paths:
            file_name = Path(file_path).name
            logger.info(f"Processing {file_name}")

            try:
                # Process file with retry logic (decorator handles retries)
                file_chunks, file_oversized, file_processed, file_split_dist = _process_single_file(
                    file_path, ctx
                )

                # Update statistics
                total_chunks += file_chunks
                oversized_articles += file_oversized
                files_processed += file_processed

                for reason, count in file_split_dist.items():
                    split_distribution[reason] += count

            except Exception as e:
                logger.error(f"Failed to process {file_name}: {e}", exc_info=True)
                files_failed += 1
                failed_files.append(file_path)

    output_size_mb = ctx.chunk_writer.get_file_size_mb()
    success_rate = (files_processed / len(changed_file_paths) * 100) if changed_file_paths else 0

    logger.info(f"✓ Processed {files_processed} files successfully")
    logger.info(f"✓ Extracted {total_chunks} chunks")
    logger.info(f"✓ Output size: {output_size_mb:.2f} MB")
    logger.info(f"✓ Split distribution: {dict(split_distribution)}")

    if files_failed > 0:
        logger.warning(f"⚠ {files_failed} files failed to process")

    return {
        "files_processed": files_processed,
        "files_failed": files_failed,
        "total_chunks": total_chunks,
        "oversized_articles": oversized_articles,
        "output_size_mb": output_size_mb,
        "success_rate": success_rate,
        "split_distribution": dict(split_distribution),
        "failed_files": failed_files[:10] if failed_files else [],
    }


def embed_chunks(changed_file_paths: list[str], force_reembed: bool = False) -> dict:
    """Generate embeddings for chunks using OpenAI.

    Args:
        changed_file_paths: List of changed file paths
        force_reembed: If True, re-embed all chunks

    Returns:
        Statistics dictionary with embedding results
    """
    ctx = _create_context()
    logger.info("Starting chunk embedding")

    # Determine which files need embedding using manifest
    files_to_embed = []
    for file_path in changed_file_paths:
        document_id = Path(file_path).stem

        if force_reembed:
            # Force re-embed everything
            files_to_embed.append(file_path)
        elif not ctx.manifest.is_stage_completed(document_id, "embedding"):
            # Never embedded or failed
            files_to_embed.append(file_path)
        else:
            # Check if hash changed since embedding
            doc_state = ctx.manifest.get_document(document_id)
            if doc_state:
                # Get current hash from lovlig
                for changed_file in ctx.lovlig_client.get_changed_files():
                    if changed_file.document_id == document_id:
                        if changed_file.file_hash != doc_state.current_version.file_hash:
                            # Hash changed, needs re-embedding
                            files_to_embed.append(file_path)
                        break

    logger.info(f"Embedding chunks from {len(files_to_embed)} files")

    # Read chunks
    chunks = list(ctx.chunk_reader.read_chunks(file_paths=set(files_to_embed)))

    if not chunks:
        logger.info("No chunks to embed")
        return {"embedded_chunks": 0, "embedded_files": 0}

    logger.info(f"Loaded {len(chunks)} chunks for embedding")

    # Batch embed with OpenAI
    batch_size = ctx.settings.embedding_batch_size
    all_embeddings = []

    for i in range(0, len(chunks), batch_size):
        batch_texts = [chunk.text for chunk in chunks[i : i + batch_size]]

        response = ctx.openai_client.embeddings.create(
            input=batch_texts, model=ctx.settings.embedding_model
        )

        batch_embeddings = [item.embedding for item in response.data]
        all_embeddings.extend(batch_embeddings)

        logger.info(f"Embedded batch {i // batch_size + 1}: {len(batch_texts)} chunks")

    # Write enriched chunks
    ctx.settings.enriched_data_dir.mkdir(parents=True, exist_ok=True)
    enriched_writer = ctx.get_enriched_chunk_writer()

    embedded_at = datetime.now(UTC).isoformat()
    with enriched_writer:
        for chunk, embedding in zip(chunks, all_embeddings, strict=True):
            # Ensure dataset_name is set for file_path reconstruction
            dataset_name = chunk.dataset_name
            if not dataset_name:
                # Try to infer from lovlig state
                for changed_file in ctx.lovlig_client.get_changed_files():
                    if changed_file.document_id == chunk.document_id:
                        dataset_name = changed_file.dataset_name
                        break

            # Create EnrichedChunk with embedding
            enriched_chunk = EnrichedChunk(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                dataset_name=dataset_name,
                content=chunk.content,
                token_count=chunk.token_count,
                section_heading=chunk.section_heading,
                absolute_address=chunk.absolute_address,
                split_reason=chunk.split_reason,
                parent_chunk_id=chunk.parent_chunk_id,
                embedding=embedding,
                embedding_model=ctx.settings.embedding_model,
                embedded_at=embedded_at,
            )
            enriched_writer.write_chunk(enriched_chunk.model_dump())

    # Mark files as embedded in manifest
    file_doc_ids = {}
    chunks_per_file = {}
    for chunk in chunks:
        doc_id = chunk.document_id
        chunks_per_file[doc_id] = chunks_per_file.get(doc_id, 0) + 1

    for file_path in files_to_embed:
        document_id = Path(file_path).stem
        file_doc_ids[file_path] = document_id

    for file_path, document_id in file_doc_ids.items():
        # Get file hash
        file_hash = "unknown"
        for changed_file in ctx.lovlig_client.get_changed_files():
            if changed_file.document_id == document_id:
                file_hash = changed_file.file_hash
                break

        # Mark embedding stage complete
        try:
            ctx.manifest.ensure_document(
                document_id=document_id,
                dataset_name="",  # Will be updated if needed
                relative_path=file_path,
                file_hash=file_hash,
                file_size_bytes=0,
            )
            ctx.manifest.complete_stage(
                document_id=document_id,
                file_hash=file_hash,
                stage="embedding",
                output={"embedded_chunks": chunks_per_file.get(document_id, 0)},
                metadata={
                    "embedded_at": datetime.now(UTC).isoformat(),
                    "model": ctx.settings.embedding_model,
                },
            )
        except ValueError:
            # Document/hash mismatch, skip
            pass

    ctx.manifest.save()

    logger.info(f"Embedding complete: {len(chunks)} chunks from {len(files_to_embed)} files")

    return {"embedded_chunks": len(chunks), "embedded_files": len(files_to_embed)}


def index_embeddings(changed_file_paths: list[str], removed_file_metadata: list[dict]) -> dict:
    """Index embeddings in ChromaDB vector database.

    Args:
        changed_file_paths: List of changed file paths
        removed_file_metadata: List of removal info for cleanup

    Returns:
        Statistics dictionary with indexing results
    """
    ctx = _create_context()
    logger.info("Starting vector indexing")

    changed_paths = set(changed_file_paths)
    removed_paths = {r["file_path"] for r in removed_file_metadata}

    logger.info(f"Indexing {len(changed_paths)} changed files")
    logger.info(f"Removing {len(removed_paths)} deleted files")

    # Delete vectors for removed files
    deleted_chunks = 0
    for file_path in removed_paths:
        count = ctx.chroma_client.delete_by_file_path(file_path)
        deleted_chunks += count
        # Extract document_id from file_path
        document_id = Path(file_path).stem
        with contextlib.suppress(ValueError):
            # Document not in manifest yet, skip
            ctx.manifest.set_index_status(document_id, IndexStatus.DELETED)

    # Delete old vectors for modified files
    changed_files = ctx.lovlig_client.get_changed_files()
    modified_paths = {str(f.absolute_path) for f in changed_files if f.status == "modified"}

    for file_path in modified_paths:
        count = ctx.chroma_client.delete_by_file_path(file_path)
        deleted_chunks += count

    # Read enriched chunks
    enriched_reader = ctx.get_enriched_chunk_reader()
    chunks = list(enriched_reader.read_chunks(file_paths=changed_paths))

    if not chunks:
        logger.info("No chunks to index")
        return {"indexed_chunks": 0, "deleted_chunks": deleted_chunks}

    logger.info(f"Loaded {len(chunks)} enriched chunks for indexing")

    # Upsert to ChromaDB
    ctx.chroma_client.upsert(chunks)

    # Update manifest
    file_chunk_counts = {}
    for chunk in chunks:
        # Count chunks per document_id (not file_path which doesn't exist in model)
        document_id = chunk.document_id
        file_chunk_counts[document_id] = file_chunk_counts.get(document_id, 0) + 1

    for document_id, _chunk_count in file_chunk_counts.items():
        with contextlib.suppress(ValueError):
            # Document not in manifest, skip
            ctx.manifest.set_index_status(document_id, IndexStatus.INDEXED)

    logger.info(f"Indexing complete: {len(chunks)} chunks indexed")

    return {"indexed_chunks": len(chunks), "deleted_chunks": deleted_chunks}


def reconcile_index() -> dict[str, Any]:
    """Reconcile index with current lovlig state - detect and remove ghost documents.

    Ghost documents are chunks in the ChromaDB index that reference files
    no longer present in lovlig's state (removed upstream).

    Returns:
        Dictionary with reconciliation statistics
    """
    ctx = _create_context()
    logger.info("Starting index reconciliation")

    # Get all file paths currently in the index
    collection = ctx.chroma_client.collection
    all_results = collection.get(include=["metadatas"])

    indexed_file_paths = set()
    if all_results and all_results["metadatas"]:
        for metadata in all_results["metadatas"]:
            if metadata and "file_path" in metadata:
                indexed_file_paths.add(metadata["file_path"])

    logger.info(f"Found {len(indexed_file_paths)} unique files in index")

    # Get current files from lovlig state
    current_state = ctx.lovlig_client._load_state()
    current_file_paths = set()

    for dataset in current_state.get("datasets", {}).values():
        for file_rel_path in dataset.get("files", {}):
            # Reconstruct absolute path
            dataset_name = dataset["name"].replace(".tar.bz2", "")
            abs_path = ctx.settings.extracted_data_dir / dataset_name / file_rel_path
            current_file_paths.add(str(abs_path))

    logger.info(f"Found {len(current_file_paths)} files in lovlig state")

    # Find ghost files (in index but not in lovlig)
    ghost_files = indexed_file_paths - current_file_paths

    if not ghost_files:
        logger.info("✓ No ghost documents found - index is clean")
        return {
            "indexed_files": len(indexed_file_paths),
            "current_files": len(current_file_paths),
            "ghost_files_found": 0,
            "chunks_deleted": 0,
        }

    logger.warning(f"Found {len(ghost_files)} ghost files in index")

    # Delete chunks for ghost files
    for idx, ghost_file in enumerate(ghost_files, start=1):
        logger.info(f"Removing ghost document {idx}/{len(ghost_files)}: {ghost_file}")
        # Delete all chunks with this file_path
        collection.delete(where={"file_path": ghost_file})

    logger.info(f"✓ Reconciliation complete: removed {len(ghost_files)} ghost files")

    return {
        "indexed_files": len(indexed_file_paths),
        "current_files": len(current_file_paths),
        "ghost_files_found": len(ghost_files),
        "ghost_files_deleted": len(ghost_files),
    }
