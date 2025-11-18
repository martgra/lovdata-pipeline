"""Embedding service for batch processing and token management.

This service encapsulates business logic for:
- Token-aware batching
- Batch size optimization
- Oversized chunk detection
- Memory-efficient batch creation
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from lovdata_pipeline.utils import estimate_tokens

if TYPE_CHECKING:
    from lovdata_pipeline.parsers import LegalChunk


@dataclass
class BatchResult:
    """Result of batch creation.

    Attributes:
        batches: List of chunk batches that fit within limits
        oversized_chunks: Chunks that exceed max_tokens_per_chunk
        total_chunks: Total number of chunks processed
        avg_batch_size: Average number of chunks per batch
    """

    batches: list[list[LegalChunk]]
    oversized_chunks: list[LegalChunk]
    total_chunks: int
    avg_batch_size: float


class EmbeddingService:
    """Service for embedding generation business logic.

    This service provides methods for batching chunks with token awareness,
    ensuring API limits are respected while maximizing throughput.

    OpenAI Batch Limits (as of 2024):
    - Max inputs per request: 2,048
    - Max tokens per request: 300,000 (embeddings endpoint)
    - text-embedding-3-large: ~8k token limit per input
    """

    @staticmethod
    def create_token_aware_batches(
        chunks: list[LegalChunk],
        max_batch_size: int,
        max_tokens_per_chunk: int = 8192,
        max_tokens_per_batch: int = 250_000,
    ) -> BatchResult:
        """Create batches that respect both size and token limits.

        This is a memory-efficient implementation that processes chunks
        sequentially without duplicating data.

        Args:
            chunks: List of chunks to batch (not copied, references only)
            max_batch_size: Maximum number of chunks per batch (OpenAI limit: 2,048)
            max_tokens_per_chunk: Maximum tokens for individual chunk (OpenAI limit: 8,192)
            max_tokens_per_batch: Maximum total tokens per batch (OpenAI limit: 300,000)

        Returns:
            BatchResult with batches and oversized chunks
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

        # Calculate statistics
        total_chunks = len(chunks)
        avg_batch_size = (
            (total_chunks - len(oversized_chunks)) / len(batches) if batches else 0.0
        )

        return BatchResult(
            batches=batches,
            oversized_chunks=oversized_chunks,
            total_chunks=total_chunks,
            avg_batch_size=avg_batch_size,
        )

    @staticmethod
    def estimate_batch_tokens(chunks: list[LegalChunk]) -> int:
        """Estimate total tokens in a batch of chunks.

        Args:
            chunks: List of chunks

        Returns:
            Estimated total token count
        """
        return sum(estimate_tokens(chunk.content) for chunk in chunks)

    @staticmethod
    def validate_batch_limits(
        batch_size: int,
        tokens_per_chunk: int,
        tokens_per_batch: int,
    ) -> tuple[bool, str]:
        """Validate batch configuration against OpenAI limits.

        Args:
            batch_size: Requested batch size
            tokens_per_chunk: Maximum tokens per chunk
            tokens_per_batch: Maximum tokens per batch

        Returns:
            Tuple of (is_valid, error_message)
        """
        errors = []

        # OpenAI limits
        MAX_BATCH_SIZE = 2048
        MAX_TOKENS_PER_CHUNK = 8192
        MAX_TOKENS_PER_BATCH = 300_000

        if batch_size > MAX_BATCH_SIZE:
            errors.append(
                f"Batch size {batch_size} exceeds OpenAI limit of {MAX_BATCH_SIZE}"
            )

        if tokens_per_chunk > MAX_TOKENS_PER_CHUNK:
            errors.append(
                f"Tokens per chunk {tokens_per_chunk} exceeds OpenAI limit of {MAX_TOKENS_PER_CHUNK}"
            )

        if tokens_per_batch > MAX_TOKENS_PER_BATCH:
            errors.append(
                f"Tokens per batch {tokens_per_batch} exceeds OpenAI limit of {MAX_TOKENS_PER_BATCH}"
            )

        if errors:
            return False, "; ".join(errors)

        return True, ""

    @staticmethod
    def calculate_optimal_batch_size(
        avg_tokens_per_chunk: int,
        max_tokens_per_batch: int = 250_000,
        max_batch_size: int = 2048,
    ) -> int:
        """Calculate optimal batch size based on token averages.

        Args:
            avg_tokens_per_chunk: Average tokens per chunk
            max_tokens_per_batch: Maximum tokens per batch
            max_batch_size: Maximum batch size

        Returns:
            Recommended batch size
        """
        if avg_tokens_per_chunk <= 0:
            return max_batch_size

        # Calculate how many chunks would fit in token budget
        optimal_size = max_tokens_per_batch // avg_tokens_per_chunk

        # Don't exceed max batch size
        return min(optimal_size, max_batch_size)
