"""Transformation assets for embedding generation.

This module contains Dagster assets for:
- Generating embeddings using OpenAI
- Implementing batching and rate limiting with token-aware batching
- Integrating Langfuse observability
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path

from dagster import asset
from dagster_openai import OpenAIResource
from langfuse import get_client, observe

from lovdata_pipeline.resources import ChromaDBResource
from lovdata_pipeline.services import CheckpointService, EmbeddingService, FileService
from lovdata_pipeline.utils import estimate_tokens


@asset(group_name="transformation", compute_kind="openai")
@observe(name="generate-embeddings-batch")
def document_embeddings(
    context,
    openai: OpenAIResource,
    chromadb: ChromaDBResource,
    parsed_legal_chunks: dict,
) -> dict:
    """Generate embeddings for legal chunks using OpenAI API with streaming.

    This asset generates embeddings with optimized batching and streaming:
    - Processes chunks in batches without loading all into memory
    - Writes to ChromaDB immediately after each batch
    - Checkpoint stores only processed IDs (not full embeddings)
    - Memory-efficient: processes one batch at a time
    - Resumable: can restart from last successful batch

    OpenAI Batch Limits (as of 2024):
    - Max inputs per request: 2,048
    - Max tokens per request: 300,000 (embeddings endpoint)
    - text-embedding-3-large: ~8k token limit per input

    Environment Variables:
    - EMBEDDING_BATCH_SIZE: Number of texts per API request (default: 2048, max: 2048)
    - EMBEDDING_RATE_LIMIT_DELAY: Seconds between batches (default: 0.5)

    Args:
        context: Dagster execution context
        openai: OpenAI resource for API access
        parsed_legal_chunks: Dict with chunks_file path and total_chunks
        chromadb: ChromaDB resource for immediate writes

    Returns:
        Dict with statistics about processed embeddings
    """
    import os

    # Load chunks from file using FileService
    chunks_file = Path(parsed_legal_chunks["chunks_file"])
    total_chunks = parsed_legal_chunks["total_chunks"]

    if not chunks_file.exists() or total_chunks == 0:
        context.log.info("No chunks to embed")
        return {"total_embeddings": 0, "batches_processed": 0}

    context.log.info(f"Processing {total_chunks} chunks from {chunks_file} (streaming)...")

    # Load all chunks using FileService (memory-efficient streaming)
    all_chunks = FileService.load_all_chunks(chunks_file)

    context.log.info(f"Loaded {len(all_chunks)} chunks, will process in streaming batches")

    # Configurable batch size with validation
    max_batch_size = min(int(os.getenv("EMBEDDING_BATCH_SIZE", "2048")), 2048)
    max_tokens_per_chunk = int(os.getenv("EMBEDDING_MAX_TOKENS_PER_CHUNK", "8192"))
    max_tokens_per_batch = int(os.getenv("EMBEDDING_MAX_TOKENS_PER_BATCH", "250000"))
    rate_limit_delay = float(os.getenv("EMBEDDING_RATE_LIMIT_DELAY", "0.5"))
    max_retries = 3
    enable_checkpointing = os.getenv("ENABLE_EMBEDDING_CHECKPOINT", "true").lower() == "true"

    # Initialize checkpoint service for resume capability
    checkpoint_service = CheckpointService(checkpoint_dir=Path("data/checkpoints"))

    context.log.info(
        f"Embedding configuration: max_batch_size={max_batch_size}, "
        f"max_tokens_per_chunk={max_tokens_per_chunk}, "
        f"max_tokens_per_batch={max_tokens_per_batch:,}, "
        f"rate_limit_delay={rate_limit_delay}s, max_retries={max_retries}"
    )

    langfuse = get_client()
    langfuse.update_current_trace(
        name="lovdata-embedding-pipeline",
        session_id=str(context.run_id),
        tags=["legal", "embeddings", "lovdata"],
    )

    # Create token-aware batches using EmbeddingService
    context.log.info(f"Creating token-aware batches for {len(all_chunks)} chunks...")
    batch_result = EmbeddingService.create_token_aware_batches(
        all_chunks, max_batch_size, max_tokens_per_chunk, max_tokens_per_batch
    )
    batches = batch_result.batches
    oversized_chunks = batch_result.oversized_chunks
    total_batches = len(batches)

    if oversized_chunks:
        context.log.warning(
            f"Found {len(oversized_chunks)} chunks exceeding {max_tokens_per_chunk} tokens. "
            "These will be skipped and logged. Consider splitting these documents into smaller chunks."
        )
        for chunk in oversized_chunks:
            context.log.warning(
                f"Oversized chunk: {chunk.chunk_id} "
                f"(~{chunk.metadata.get('estimated_tokens', 'unknown')} tokens)"
            )

    context.log.info(
        f"Created {total_batches} batches for {batch_result.total_chunks - len(oversized_chunks)} chunks "
        f"(avg {batch_result.avg_batch_size:.1f} chunks/batch)"
    )

    # Load checkpoint if exists and checkpointing is enabled
    total_embedded = 0
    start_batch = 1
    processed_chunk_ids = set()

    if enable_checkpointing:
        checkpoint = checkpoint_service.load(run_id=str(context.run_id), operation="embeddings")
        if checkpoint:
            start_batch = checkpoint.last_batch + 1
            processed_chunk_ids = checkpoint.processed_ids
            total_embedded = checkpoint.total_processed

            context.log.info(
                f"Resuming from checkpoint: {total_embedded} chunks already embedded, "
                f"starting from batch {start_batch}/{total_batches}"
            )

    # Get ChromaDB collection for streaming writes
    collection = chromadb.get_or_create_collection()

    with openai.get_client(context) as client:
        for batch_num, batch in enumerate(batches, 1):
            # Skip already processed batches
            if batch_num < start_batch:
                continue

            # Filter out already processed chunks (in case of partial batch)
            batch = [c for c in batch if c.chunk_id not in processed_chunk_ids]
            if not batch:
                context.log.info(f"Batch {batch_num} already processed, skipping")
                continue

            batch_texts = [c.content for c in batch]
            estimated_tokens = sum(estimate_tokens(text) for text in batch_texts)

            if batch_num % 10 == 0 or batch_num == 1:
                context.log.info(
                    f"Processing batch {batch_num}/{total_batches} "
                    f"({len(batch)} chunks, ~{estimated_tokens:,} tokens)..."
                )

            # Generate embeddings with retry
            retries = 0

            while retries < max_retries:
                try:
                    with langfuse.start_as_current_observation(
                        as_type="embedding", name=f"batch-{batch_num}"
                    ) as obs:
                        response = client.embeddings.create(
                            model="text-embedding-3-large",
                            input=batch_texts,
                            dimensions=1536,  # Optional: reduce for storage efficiency
                        )

                        obs.update(
                            metadata={
                                "batch_index": batch_num,
                                "batch_size": len(batch_texts),
                                "total_tokens": response.usage.total_tokens,
                            },
                            usage={
                                "input": response.usage.prompt_tokens,
                                "total": response.usage.total_tokens,
                            },
                        )

                    # Prepare batch data for ChromaDB
                    batch_ids = []
                    batch_embeddings = []
                    batch_documents = []
                    batch_metadatas = []

                    for chunk, embedding_data in zip(batch, response.data, strict=False):
                        chunk.metadata["embedding_model"] = "text-embedding-3-large"
                        chunk.metadata["embedding_generated_at"] = datetime.now(UTC).isoformat()

                        batch_ids.append(chunk.chunk_id)
                        batch_embeddings.append(embedding_data.embedding)
                        batch_documents.append(chunk.content)
                        batch_metadatas.append(chunk.metadata)

                    # Stream to ChromaDB immediately
                    collection.upsert(
                        ids=batch_ids,
                        embeddings=batch_embeddings,
                        documents=batch_documents,
                        metadatas=batch_metadatas,
                    )

                    total_embedded += len(batch_ids)
                    processed_chunk_ids.update(batch_ids)

                    context.log.info(
                        f"Batch {batch_num}/{total_batches}: {len(batch)} chunks embedded and written to ChromaDB, "
                        f"{response.usage.total_tokens} tokens, "
                        f"progress: {total_embedded}/{len(all_chunks)}"
                    )

                    # Save checkpoint with only IDs (not full embeddings!)
                    if enable_checkpointing:
                        success = checkpoint_service.save(
                            run_id=str(context.run_id),
                            operation="embeddings",
                            last_batch=batch_num,
                            processed_ids=processed_chunk_ids,
                            total_processed=total_embedded,
                        )
                        if not success:
                            context.log.warning("Failed to save checkpoint")

                    break

                except Exception as e:
                    retries += 1
                    error_msg = str(e).lower()

                    # Handle rate limiting with exponential backoff
                    if ("rate_limit" in error_msg or "429" in error_msg) and retries < max_retries:
                        delay = (2**retries) * 2  # 2s, 4s, 8s
                        context.log.warning(
                            f"Rate limit hit on batch {batch_num}. "
                            f"Retry {retries}/{max_retries} in {delay}s"
                        )
                        time.sleep(delay)
                    # Handle token limit errors
                    elif "token" in error_msg and "limit" in error_msg:
                        context.log.error(
                            f"Token limit exceeded in batch {batch_num}. "
                            "Adjust EMBEDDING_MAX_TOKENS or chunk sizes."
                        )
                        raise
                    else:
                        context.log.error(f"Failed batch {batch_num} (attempt {retries}): {e}")
                        if retries >= max_retries:
                            raise

            # Rate limiting between batches (only if more batches remain)
            if batch_num < total_batches:
                time.sleep(rate_limit_delay)

    # Flush Langfuse events
    langfuse.flush()

    # Clean up checkpoint file on successful completion
    if enable_checkpointing:
        if checkpoint_service.delete(run_id=str(context.run_id), operation="embeddings"):
            context.log.info("Checkpoint cleaned up after successful completion")
        else:
            context.log.warning("Failed to clean up checkpoint")

    # Clean up temporary chunks file using FileService
    deleted = FileService.cleanup_temp_files(chunks_file)
    if deleted:
        context.log.info(f"Cleaned up temp files: {deleted}")

    # Verify final count
    final_collection_count = collection.count()

    context.add_output_metadata(
        {
            "total_embeddings": total_embedded,
            "collection_count": final_collection_count,
            "embedding_model": "text-embedding-3-large",
            "embedding_dimension": 1536,
            "batches_processed": total_batches,
            "max_batch_size": max_batch_size,
            "max_tokens_per_batch": max_tokens_per_batch,
            "rate_limit_delay": rate_limit_delay,
            "oversized_chunks_skipped": len(oversized_chunks),
            "avg_chunks_per_batch": (total_embedded / total_batches if total_batches > 0 else 0),
        }
    )

    return {
        "total_embeddings": total_embedded,
        "batches_processed": total_batches,
        "collection_count": final_collection_count,
        "status": "success",
    }
