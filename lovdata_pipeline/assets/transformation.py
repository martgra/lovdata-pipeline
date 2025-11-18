"""Transformation assets for embedding generation.

This module contains Dagster assets for:
- Generating embeddings using OpenAI
- Implementing batching and rate limiting with token-aware batching
- Integrating Langfuse observability
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path

from dagster import asset
from dagster_openai import OpenAIResource
from langfuse import get_client, observe

from lovdata_pipeline.parsers import LegalChunk
from lovdata_pipeline.resources import ChromaDBResource


def estimate_tokens(text: str) -> int:
    """Estimate token count for text (approximation: 1 token ≈ 4 characters)."""
    return len(text) // 4


def create_token_aware_batches(
    chunks: list[LegalChunk],
    max_batch_size: int,
    max_tokens_per_chunk: int = 8192,
    max_tokens_per_batch: int = 250_000,
) -> tuple[list[list[LegalChunk]], list[LegalChunk]]:
    """Create batches that respect both size and token limits.

    Args:
        chunks: List of chunks to batch
        max_batch_size: Maximum number of chunks per batch (OpenAI limit: 2,048)
        max_tokens_per_chunk: Maximum tokens for individual chunk (OpenAI limit: 8,192)
        max_tokens_per_batch: Maximum total tokens per batch (OpenAI limit: 300,000)

    Returns:
        Tuple of (batches, oversized_chunks)
        - batches: List of chunk batches that fit within limits
        - oversized_chunks: Chunks that exceed max_tokens_per_chunk individually
    """
    batches = []
    current_batch = []
    current_tokens = 0
    oversized_chunks = []

    for chunk in chunks:
        chunk_tokens = estimate_tokens(chunk.content)

        # If single chunk exceeds per-chunk limit, skip it and track for reporting
        if chunk_tokens > max_tokens_per_chunk:
            chunk.metadata["oversized"] = True
            chunk.metadata["estimated_tokens"] = chunk_tokens
            oversized_chunks.append(chunk)
            continue  # Skip this chunk - don't add to any batch

        # Start new batch if adding this chunk would exceed limits
        if current_batch and (
            len(current_batch) >= max_batch_size
            or current_tokens + chunk_tokens > max_tokens_per_batch
        ):
            batches.append(current_batch)
            current_batch = []
            current_tokens = 0

        current_batch.append(chunk)
        current_tokens += chunk_tokens

    # Add final batch
    if current_batch:
        batches.append(current_batch)

    return batches, oversized_chunks


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
    import pickle

    # Load chunks from file
    chunks_file = Path(parsed_legal_chunks["chunks_file"])
    total_chunks = parsed_legal_chunks["total_chunks"]

    if not chunks_file.exists() or total_chunks == 0:
        context.log.info("No chunks to embed")
        return {"total_embeddings": 0, "batches_processed": 0}

    context.log.info(f"Processing {total_chunks} chunks from {chunks_file} (streaming)...")

    # Load all chunks into batches (but we'll process one at a time)
    all_chunks = []
    with open(chunks_file, "rb") as f:
        while True:
            try:
                batch_chunks = pickle.load(f)
                all_chunks.extend(batch_chunks)
            except EOFError:
                break

    context.log.info(f"Loaded {len(all_chunks)} chunks, will process in streaming batches")

    # Configurable batch size with validation
    max_batch_size = min(int(os.getenv("EMBEDDING_BATCH_SIZE", "2048")), 2048)
    max_tokens_per_chunk = int(os.getenv("EMBEDDING_MAX_TOKENS_PER_CHUNK", "8192"))
    max_tokens_per_batch = int(os.getenv("EMBEDDING_MAX_TOKENS_PER_BATCH", "250000"))
    rate_limit_delay = float(os.getenv("EMBEDDING_RATE_LIMIT_DELAY", "0.5"))
    max_retries = 3
    enable_checkpointing = os.getenv("ENABLE_EMBEDDING_CHECKPOINT", "true").lower() == "true"

    # Checkpoint file for resume capability
    checkpoint_dir = Path("data/checkpoints")
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_file = checkpoint_dir / f"embeddings_{context.run_id}.json"

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

    # Create token-aware batches
    context.log.info(f"Creating token-aware batches for {len(all_chunks)} chunks...")
    batches, oversized_chunks = create_token_aware_batches(
        all_chunks, max_batch_size, max_tokens_per_chunk, max_tokens_per_batch
    )
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
        f"Created {total_batches} batches for {len(parsed_legal_chunks) - len(oversized_chunks)} chunks "
        f"(avg {(len(parsed_legal_chunks) - len(oversized_chunks)) / total_batches:.1f} chunks/batch)"
    )

    # Load checkpoint if exists and checkpointing is enabled
    total_embedded = 0
    start_batch = 1
    processed_chunk_ids = set()

    if enable_checkpointing and checkpoint_file.exists():
        try:
            with open(checkpoint_file) as f:
                checkpoint = json.load(f)
                start_batch = checkpoint.get("last_batch", 0) + 1
                processed_chunk_ids = set(checkpoint.get("processed_chunk_ids", []))
                total_embedded = len(processed_chunk_ids)

            context.log.info(
                f"Resuming from checkpoint: {total_embedded} chunks already embedded, "
                f"starting from batch {start_batch}/{total_batches}"
            )
        except Exception as e:
            context.log.warning(f"Failed to load checkpoint: {e}. Starting from scratch.")
            total_embedded = 0
            start_batch = 1
            processed_chunk_ids = set()

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
                        try:
                            checkpoint_data = {
                                "last_batch": batch_num,
                                "processed_chunk_ids": list(processed_chunk_ids),
                                "timestamp": datetime.now(UTC).isoformat(),
                                "total_embedded": total_embedded,
                            }
                            with open(checkpoint_file, "w") as f:
                                json.dump(checkpoint_data, f)
                        except Exception as e:
                            context.log.warning(f"Failed to save checkpoint: {e}")

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
    if enable_checkpointing and checkpoint_file.exists():
        try:
            checkpoint_file.unlink()
            context.log.info("Checkpoint cleaned up after successful completion")
        except Exception as e:
            context.log.warning(f"Failed to clean up checkpoint: {e}")

    # Clean up temporary chunks file
    try:
        chunks_file.unlink()
        context.log.info(f"Cleaned up chunks file: {chunks_file}")
    except Exception as e:
        context.log.warning(f"Failed to clean up chunks file: {e}")

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
