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


@pytest.mark.parametrize(
    "api_key,expected_error",
    [
        ("", "OPENAI_API_KEY"),  # Empty string - missing required field
        ("invalid-key", "must start with 'sk-'"),  # Invalid format
        ("sk-short", "too short"),  # Too short
    ],
    ids=["missing", "invalid_format", "too_short"],
)
def test_settings_api_key_validation(monkeypatch, api_key, expected_error):
    """Test API key validation with various invalid inputs."""
    # Clear existing API key env vars
    for key in list(os.environ.keys()):
        if "API_KEY" in key.upper() or key.upper() == "OPENAI_API_KEY":
            monkeypatch.delenv(key, raising=False)

    if api_key:  # Only set if not testing empty
        monkeypatch.setenv("OPENAI_API_KEY", api_key)
    else:
        monkeypatch.setenv("OPENAI_API_KEY", "")

    with pytest.raises(ValidationError) as exc_info:
        PipelineSettings()

    errors = exc_info.value.errors()
    # Verify expected error is present
    assert any(expected_error in str(e) for e in errors)


@pytest.mark.parametrize(
    "chunk_tokens,should_pass,expected_value",
    [
        (50, False, None),      # Too small
        (20000, False, None),   # Too large
        (100, True, 100),       # Valid minimum
        (6800, True, 6800),     # Valid default
        (10000, True, 10000),   # Valid maximum
    ],
    ids=["too_small", "too_large", "min_boundary", "default", "max_boundary"],
)
def test_settings_chunk_tokens_validation(monkeypatch, chunk_tokens, should_pass, expected_value):
    """Test chunk token bounds validation."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test123456789012345678")

    if should_pass:
        settings = PipelineSettings(chunk_max_tokens=chunk_tokens)
        assert settings.chunk_max_tokens == expected_value
    else:
        with pytest.raises(ValidationError):
            PipelineSettings(chunk_max_tokens=chunk_tokens)


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
