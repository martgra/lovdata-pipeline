"""Tests for pipeline settings."""

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from lovdata_pipeline.config.settings import PipelineSettings


def test_settings_from_environment(monkeypatch):
    """Test loading settings from environment variables."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test123456789012345678")  # pragma: allowlist secret
    monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-3-small")
    monkeypatch.setenv("CHUNK_MAX_TOKENS", "5000")

    settings = PipelineSettings()

    assert settings.openai_api_key == "sk-test123456789012345678"  # pragma: allowlist secret
    assert settings.embedding_model == "text-embedding-3-small"
    assert settings.chunk_max_tokens == 5000


def test_settings_with_overrides(monkeypatch):
    """Test that constructor overrides environment variables."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test123456789012345678")
    monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-3-small")

    settings = PipelineSettings(
        embedding_model="text-embedding-3-large",
        chunk_max_tokens=7000,
    )

    assert settings.openai_api_key == "sk-test123456789012345678"
    assert settings.embedding_model == "text-embedding-3-large"
    assert settings.chunk_max_tokens == 7000


def test_settings_defaults(monkeypatch):
    """Test default values."""
    # Clear all env vars and set only the required one
    for key in list(os.environ.keys()):
        if key.upper() in ["OPENAI_API_KEY", "EMBEDDING_MODEL", "DATA_DIR", "CHROMA_PATH",
                           "CHUNK_MAX_TOKENS", "DATASET_FILTER", "FORCE"]:
            monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test123456789012345678")  # pragma: allowlist secret

    # Create settings without loading .env file
    from pydantic_settings import SettingsConfigDict
    from lovdata_pipeline.config.settings import PipelineSettings

    class TestSettings(PipelineSettings):
        model_config = SettingsConfigDict(
            env_file=None,  # Don't load .env file
            extra="ignore",
            case_sensitive=False,
        )

    settings = TestSettings()

    assert settings.embedding_model == "text-embedding-3-large"
    assert settings.data_dir == Path("./data")
    assert settings.chroma_path == Path("./data/chroma")
    assert settings.chunk_max_tokens == 6800
    assert settings.dataset_filter == "gjeldende"
    assert settings.force is False


def test_settings_missing_api_key(monkeypatch):
    """Test that missing API key raises validation error."""
    # Clear all env vars including from .env file
    for key in list(os.environ.keys()):
        if "API_KEY" in key.upper() or key.upper() == "OPENAI_API_KEY":
            monkeypatch.delenv(key, raising=False)

    # Also need to prevent .env file loading
    monkeypatch.setenv("OPENAI_API_KEY", "")  # Empty string should fail validation

    with pytest.raises(ValidationError) as exc_info:
        PipelineSettings()

    errors = exc_info.value.errors()
    # Field location uses the alias (OPENAI_API_KEY) in errors
    assert any(e["loc"] == ("OPENAI_API_KEY",) for e in errors)


def test_settings_invalid_api_key(monkeypatch):
    """Test that invalid API key format raises validation error."""
    monkeypatch.setenv("OPENAI_API_KEY", "invalid-key")  # pragma: allowlist secret

    with pytest.raises(ValidationError) as exc_info:
        PipelineSettings()

    errors = exc_info.value.errors()
    # Field location uses the alias (OPENAI_API_KEY) in errors
    assert any(
        e["loc"] == ("OPENAI_API_KEY",) and "must start with 'sk-'" in e["msg"]
        for e in errors
    )


def test_settings_api_key_too_short(monkeypatch):
    """Test that short API key raises validation error."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-short")

    with pytest.raises(ValidationError) as exc_info:
        PipelineSettings()

    errors = exc_info.value.errors()
    # Field location uses the alias (OPENAI_API_KEY) in errors
    assert any(
        e["loc"] == ("OPENAI_API_KEY",) and "too short" in e["msg"]
        for e in errors
    )


def test_settings_chunk_tokens_validation(monkeypatch):
    """Test chunk token bounds validation."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test123456789012345678")

    # Too small
    with pytest.raises(ValidationError):
        PipelineSettings(chunk_max_tokens=50)

    # Too large
    with pytest.raises(ValidationError):
        PipelineSettings(chunk_max_tokens=20000)

    # Valid boundaries
    settings_min = PipelineSettings(chunk_max_tokens=100)
    assert settings_min.chunk_max_tokens == 100

    settings_max = PipelineSettings(chunk_max_tokens=10000)
    assert settings_max.chunk_max_tokens == 10000


def test_settings_empty_dataset_filter(monkeypatch):
    """Test that empty dataset filter raises validation error."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test123456789012345678")

    with pytest.raises(ValidationError) as exc_info:
        PipelineSettings(dataset_filter="")

    errors = exc_info.value.errors()
    assert any(
        e["loc"] == ("dataset_filter",) and "cannot be empty" in e["msg"]
        for e in errors
    )


def test_settings_path_conversion(monkeypatch):
    """Test that string paths are converted to Path objects."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test123456789012345678")  # pragma: allowlist secret

    settings = PipelineSettings(
        data_dir="/tmp/data",
        chroma_path="/tmp/chroma",
    )

    assert isinstance(settings.data_dir, Path)
    assert isinstance(settings.chroma_path, Path)
    assert settings.data_dir == Path("/tmp/data")
    assert settings.chroma_path == Path("/tmp/chroma")


def test_settings_case_insensitive(monkeypatch):
    """Test that environment variables are case-insensitive."""
    monkeypatch.setenv("openai_api_key", "sk-test123456789012345678")  # pragma: allowlist secret
    monkeypatch.setenv("embedding_model", "text-embedding-3-small")

    settings = PipelineSettings()

    assert settings.openai_api_key == "sk-test123456789012345678"
    assert settings.embedding_model == "text-embedding-3-small"


def test_settings_dataset_filter_whitespace(monkeypatch):
    """Test that dataset filter whitespace is stripped."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test123456789012345678")

    settings = PipelineSettings(dataset_filter="  gjeldende-lover  ")

    assert settings.dataset_filter == "gjeldende-lover"
