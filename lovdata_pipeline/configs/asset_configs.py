"""Configuration schemas for pipeline assets.

This module defines Dagster Config classes that provide:
- Type-safe configuration with validation
- Default values aligned with production settings
- Documentation for each config field
- Integration with Dagster UI for runtime configuration
"""

from __future__ import annotations

from dagster import Config


class IngestionConfig(Config):
    """Configuration for ingestion assets.

    Controls file processing limits and batch sizes during the ingestion phase.
    """

    max_files: int = 0
    """Maximum number of files to process (0 = unlimited).

    Useful for testing or limiting processing scope. Set to a positive
    integer to process only the first N changed files.
    """

    file_batch_size: int = 100
    """Number of files to process in each batch.

    Files are processed in batches to manage memory usage and enable
    progress tracking. Larger batches = faster but more memory.
    """


class ParsingConfig(Config):
    """Configuration for XML parsing.

    Controls token limits and overlap for chunk splitting during parsing.
    """

    max_tokens: int = 6800
    """Maximum tokens per chunk (safe limit for 8K context).

    Chunks exceeding this limit will be split. Conservative default
    (6800) provides safety margin below OpenAI's 8K limit for
    text-embedding-3-large.
    """

    overlap_tokens: int = 100
    """Token overlap between split chunks.

    When chunks are split due to size limits, this overlap ensures
    context continuity across boundaries. Higher values improve
    context preservation but increase total tokens.
    """


class EmbeddingConfig(Config):
    """Configuration for embedding generation.

    Controls batching, token limits, rate limiting, and checkpointing
    for the embedding generation process.
    """

    batch_size: int = 2048
    """Number of chunks per OpenAI API request (max: 2048).

    OpenAI allows up to 2,048 inputs per embeddings request.
    Larger batches = fewer API calls but longer wait times.
    """

    max_tokens_per_chunk: int = 8192
    """Maximum tokens for individual chunk (OpenAI limit: 8,192).

    Chunks exceeding this will be flagged as oversized and skipped.
    This is a hard limit enforced by OpenAI's API.
    """

    max_tokens_per_batch: int = 250_000
    """Maximum total tokens per batch (OpenAI limit: 300,000).

    Conservative default (250K) provides safety margin below
    OpenAI's 300K limit. Batches are created respecting both
    this limit and batch_size.
    """

    rate_limit_delay: float = 0.5
    """Delay in seconds between API batches.

    Helps avoid rate limits. Increase if experiencing 429 errors.
    Decrease for faster processing (with rate limit risk).
    """

    max_retries: int = 3
    """Maximum retry attempts for failed API requests.

    Requests failing due to rate limits or transient errors will
    be retried with exponential backoff up to this limit.
    """

    enable_checkpointing: bool = True
    """Enable checkpoint-based recovery for resumable operations.

    When enabled, progress is saved after each batch. If the
    process fails, it can resume from the last checkpoint.
    Disable only for testing or debugging.
    """
