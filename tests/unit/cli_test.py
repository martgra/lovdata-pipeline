"""Tests for CLI interface.

Tests only critical CLI error handling. Argument parsing is tested by Typer.
Pipeline execution is covered by integration tests.
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from lovdata_pipeline.cli import app

runner = CliRunner()


class TestProcessCommand:
    """Tests for the 'process' command - critical paths only."""

    @patch("lovdata_pipeline.cli.PipelineSettings")
    def test_process_missing_api_key(self, mock_settings_class, monkeypatch):
        """Test process command fails without API key."""
        # Clear API key
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        # Make settings raise validation error
        mock_settings_class.side_effect = ValidationError.from_exception_data(
            "Settings",
            [{"loc": ("OPENAI_API_KEY",), "msg": "Field required", "type": "missing"}],
        )

        result = runner.invoke(app, ["process"])

        assert result.exit_code == 1
        assert "Configuration Error" in result.output

    @patch("lovdata_pipeline.orchestration.pipeline_orchestrator.PipelineOrchestrator")
    @patch("lovdata_pipeline.cli.PipelineSettings")
    def test_process_pipeline_error(self, mock_settings_class, mock_orchestrator_class, monkeypatch):
        """Test process command handles pipeline errors."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test123456789012345678")

        mock_settings = Mock()
        mock_settings.dataset_filter = "gjeldende"
        mock_settings.storage_type = "chroma"
        mock_settings.openai_api_key = "sk-test123456789012345678"
        mock_settings_class.return_value = mock_settings

        # Simulate pipeline error
        mock_orchestrator_class.create.side_effect = Exception("Pipeline failed")

        result = runner.invoke(app, ["process"])

        assert result.exit_code == 1
        assert "Error: Pipeline failed" in result.output


class TestMigrateCommand:
    """Tests for the 'migrate' command validation."""

    def test_migrate_invalid_source(self):
        """Test migration with invalid source type."""
        result = runner.invoke(app, [
            "migrate",
            "--source", "invalid",
            "--target", "jsonl",
        ])

        assert result.exit_code == 1
        assert "Invalid source storage" in result.output

    def test_migrate_same_source_and_target(self):
        """Test migration fails when source equals target."""
        result = runner.invoke(app, [
            "migrate",
            "--source", "chroma",
            "--target", "chroma",
        ])

        assert result.exit_code == 1
        assert "Source and target must be different" in result.output
