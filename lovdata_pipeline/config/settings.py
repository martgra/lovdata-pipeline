"""Settings for Lovdata pipeline.

Uses pydantic-settings to load configuration from environment variables.
"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LovdataSettings(BaseSettings):
    """Configuration settings for Lovdata pipeline.

    All settings can be overridden via environment variables with LOVDATA_ prefix.

    Attributes:
        dataset_filter: Filter for datasets to sync (e.g., 'gjeldende')
        raw_data_dir: Directory for raw downloaded archives
        extracted_data_dir: Directory for extracted XML files
        state_file: Path to lovlig state.json file
        max_download_concurrency: Maximum concurrent downloads
        chunk_max_tokens: Maximum tokens per chunk for document splitting
        chunk_output_path: Path to output JSONL file for chunks
    """

    model_config = SettingsConfigDict(env_prefix="LOVDATA_", env_file=".env", extra="ignore")

    dataset_filter: str = Field(default="gjeldende", description="Dataset filter pattern")
    raw_data_dir: Path = Field(default=Path("./data/raw"), description="Raw data directory")
    extracted_data_dir: Path = Field(
        default=Path("./data/extracted"), description="Extracted data directory"
    )
    state_file: Path = Field(default=Path("./data/state.json"), description="State file path")
    max_download_concurrency: int = Field(
        default=4, ge=1, le=10, description="Max concurrent downloads"
    )
    chunk_max_tokens: int = Field(
        default=6800, ge=100, le=100000, description="Maximum tokens per chunk"
    )
    chunk_output_path: Path = Field(
        default=Path("./data/chunks/legal_chunks.jsonl"), description="Chunk output file path"
    )
    force_reprocess: bool = Field(
        default=False,
        description="Force reprocessing of all files, ignoring processed_at timestamps",
    )

    # Embedding settings
    enriched_data_dir: Path = Field(
        default=Path("./data/enriched"), description="Directory for enriched chunks with embeddings"
    )
    embedding_model: str = Field(
        default="text-embedding-3-large",
        description="OpenAI embedding model to use",
    )
    embedding_batch_size: int = Field(
        default=100, ge=1, le=2048, description="Batch size for embedding API calls"
    )
    force_reembed: bool = Field(
        default=False,
        description="Force re-embedding of all files, ignoring embedded_at timestamps",
    )
    openai_api_key: str = Field(default="", description="OpenAI API key for embeddings")

    # Vector database settings
    vector_db_type: str = Field(
        default="chroma",
        description="Vector database type (currently only 'chroma' is supported)",
    )
    vector_db_collection: str = Field(
        default="legal_docs",
        description="Collection/index name for vector database",
    )

    # ChromaDB-specific settings (used when vector_db_type='chroma')
    chroma_mode: str = Field(
        default="persistent",
        description="ChromaDB mode: 'memory', 'persistent', or 'client'",
    )
    chroma_host: str = Field(
        default="localhost",
        description="ChromaDB server host (used in 'client' mode)",
    )
    chroma_port: int = Field(
        default=8000,
        description="ChromaDB server port (used in 'client' mode)",
    )
    chroma_persist_directory: str | None = Field(
        default="./data/chroma",
        description="Local directory for persistent storage (used in 'persistent' mode)",
    )

    # Pipeline manifest
    pipeline_manifest_path: Path = Field(
        default=Path("./data/pipeline_manifest.json"),
        description="Path to pipeline manifest file",
    )

    @property
    def data_dir(self) -> Path:
        """Get the base data directory.

        Returns:
            Path to data directory
        """
        return Path("./data")


def get_settings() -> LovdataSettings:
    """Get configuration settings.

    Returns:
        LovdataSettings instance loaded from environment
    """
    return LovdataSettings()
