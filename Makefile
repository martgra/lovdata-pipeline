# Makefile for Lovdata pipeline
SHELL := /bin/bash
.DEFAULT_GOAL := install
.PHONY: install update-deps test lint format clean process status help check all

# Help target
help:
	@echo "Available targets:"
	@echo "  install       - Install dependencies (frozen)"
	@echo "  update-deps   - Update and sync dependencies"
	@echo "  test          - Run tests with pytest"
	@echo "  lint          - Check code with ruff"
	@echo "  format        - Format code with ruff"
	@echo "  process       - Run complete pipeline (atomic per-file)"
	@echo "  status        - Show pipeline status"
	@echo "  clean         - Remove cache and temporary files"

install: uv.lock
	uv sync --frozen

uv.lock: pyproject.toml
	uv sync

update-deps:
	uv sync

test:
	uv run pytest tests/

lint:
	uv run ruff check lovdata_pipeline tests

format:
	uv run ruff format lovdata_pipeline tests

process:
	uv run python -m lovdata_pipeline process

status:
	uv run python -m lovdata_pipeline status

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .coverage htmlcov/ dist/ build/
