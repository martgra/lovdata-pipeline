"""Pipeline settings with environment variable support.

Uses pydantic-settings for type-safe configuration management.
Automatically loads from .env file and validates all settings.
"""

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class PipelineSettings(BaseSettings):
    """Pipeline configuration with automatic environment variable loading.

    All settings can be overridden via environment variables.
    The .env file is automatically loaded if present.

    Examples:
        >>> # Load from environment
        >>> settings = PipelineSettings()
        >>> settings.openai_api_key
        'sk-...'

        >>> # Override specific values
        >>> settings = PipelineSettings(force=True, dataset_filter="gjeldende-lover")
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # Ignore extra env vars
        case_sensitive=False,  # Allow OPENAI_API_KEY or openai_api_key
    )

    # OpenAI Configuration
    openai_api_key: str = Field(
        ...,
        description="OpenAI API key for embeddings",
        alias="OPENAI_API_KEY",  # Support both OPENAI_API_KEY and openai_api_key
    )
    embedding_model: str = Field(
        default="text-embedding-3-large",
        description="OpenAI embedding model to use",
    )

    # Pipeline Configuration
    data_dir: Path = Field(
        default=Path("./data"),
        description="Root data directory for all pipeline data",
    )
    chroma_path: Path = Field(
        default=Path("./data/chroma"),
        description="ChromaDB persistence directory",
    )
    chunk_max_tokens: int = Field(
        default=6800,
        ge=100,
        le=10000,
        description="Maximum tokens per chunk",
    )

    # Processing Configuration
    dataset_filter: str = Field(
        default="gjeldende",
        description="Dataset filter pattern (e.g., 'gjeldende-lover', 'gjeldende-*', '*')",
    )
    force: bool = Field(
        default=False,
        description="Force reprocessing of all files",
    )

    @field_validator("data_dir", "chroma_path", mode="before")
    @classmethod
    def validate_path(cls, v) -> Path:  # pylint: disable=unused-argument  # noqa: N805
        """Convert string paths to Path objects."""
        if isinstance(v, str):
            return Path(v)
        return v

    @field_validator("openai_api_key")
    @classmethod
    def validate_api_key(cls, v: str) -> str:  # pylint: disable=unused-argument  # noqa: N805
        """Validate OpenAI API key format."""
        if not v:
            raise ValueError("OpenAI API key cannot be empty")
        if not v.startswith("sk-"):
            raise ValueError("OpenAI API key must start with 'sk-'")
        if len(v) < 20:
            raise ValueError("OpenAI API key appears to be too short")
        return v

    @field_validator("dataset_filter")
    @classmethod
    def validate_dataset_filter(cls, v: str) -> str:  # pylint: disable=unused-argument  # noqa: N805
        """Validate dataset filter pattern."""
        if not v or not v.strip():
            raise ValueError("Dataset filter cannot be empty")
        return v.strip()

    def to_dict(self) -> dict:
        """Convert settings to dictionary for backward compatibility.

        Returns:
            Dictionary with all settings as strings/primitives
        """
        return {
            "openai_api_key": self.openai_api_key,
            "embedding_model": self.embedding_model,
            "data_dir": str(self.data_dir),
            "chroma_path": str(self.chroma_path),
            "chunk_max_tokens": self.chunk_max_tokens,
            "dataset_filter": self.dataset_filter,
            "force": self.force,
        }
