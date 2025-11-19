"""Settings for Lovdata pipeline.

Uses pydantic-settings to load configuration from environment variables.

NOTE: The CLI currently uses command-line options instead of this settings module.
This module is provided for programmatic usage and advanced configurations.
"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LovdataSettings(BaseSettings):
    """Configuration settings for Lovdata pipeline.

    All settings can be overridden via environment variables with LOVDATA_ prefix.

    Attributes:
        dataset_filter: Filter for datasets to sync (e.g., 'gjeldende-lover')
        data_dir: Base data directory
        chunk_max_tokens: Maximum tokens per chunk for document splitting
        embedding_model: OpenAI embedding model
        openai_api_key: OpenAI API key for embeddings
        chroma_path: Path to ChromaDB persistent storage
        force_reprocess: Force reprocessing of all files
    """

    model_config = SettingsConfigDict(env_prefix="LOVDATA_", env_file=".env", extra="ignore")

    # Core settings
    dataset_filter: str = Field(
        default="gjeldende", description="Dataset filter pattern (gjeldende, gjeldende-lover, etc.)"
    )
    data_dir: Path = Field(default=Path("./data"), description="Base data directory")

    # Processing settings
    chunk_max_tokens: int = Field(
        default=6800, ge=100, le=100000, description="Maximum tokens per chunk"
    )

    # Embedding settings
    embedding_model: str = Field(
        default="text-embedding-3-large",
        description="OpenAI embedding model to use",
    )
    openai_api_key: str = Field(default="", description="OpenAI API key for embeddings")

    # ChromaDB settings
    chroma_path: Path = Field(
        default=Path("./data/chroma"),
        description="Path to ChromaDB persistent storage",
    )

    # Pipeline control
    force_reprocess: bool = Field(
        default=False,
        description="Force reprocessing of all files",
    )

    @property
    def raw_dir(self) -> Path:
        """Get raw data directory."""
        return self.data_dir / "raw"

    @property
    def extracted_dir(self) -> Path:
        """Get extracted data directory."""
        return self.data_dir / "extracted"

    @property
    def state_file(self) -> Path:
        """Get lovlig state file path."""
        return self.data_dir / "state.json"

    @property
    def pipeline_state_file(self) -> Path:
        """Get pipeline state file path."""
        return self.data_dir / "pipeline_state.json"


def get_settings() -> LovdataSettings:
    """Get configuration settings.

    Returns:
        LovdataSettings instance loaded from environment
    """
    return LovdataSettings()
