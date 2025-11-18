# Makefile for uv with smart install + explicit updates
SHELL := /bin/bash
.DEFAULT_GOAL := install
.PHONY: install update-deps test lint format clean run help check all secrets check-tools github-create github-push

# Help target
help:
	@echo "Available targets:"
	@echo "  install      - Install dependencies (frozen)"
	@echo "  update-deps  - Update and sync dependencies"
	@echo "  test         - Run tests with pytest"
	@echo "  lint         - Check code with ruff"
	@echo "  format       - Format code with ruff"
	@echo "  run          - Run the main application"
	@echo "  dagster      - Start Dagster dev server"
	@echo "  dagster-job  - Run Dagster processing job (uses .env or defaults)"
	@echo "  dagster-test - Run pipeline with 10 files (for testing)"
	@echo "  dagster-batch - Run pipeline with 100 files"
	@echo "  dagster-sync - Sync Lovdata datasets only (uses LOVDATA_DATASET_FILTER from .env)"
	@echo "  dagster-sync-all - Sync all Lovdata datasets (overrides filter)"
	@echo "  docker-build - Build Docker image"
	@echo "  docker-up    - Start Docker Compose"
	@echo "  docker-down  - Stop Docker Compose"
	@echo "  clean        - Remove cache and temporary files"
	@echo "  secrets      - Scan for secrets using detect-secrets"
	@echo "  check-tools  - Check if required tools are installed"
	@echo "  github-create - Create GitHub repository (requires gh CLI)"
	@echo "  github-push   - Push to GitHub (run after github-create)"


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

run:
	uv run python lovdata_pipeline/__main__.py

dagster:
	uv run dagster dev -m lovdata_pipeline

dagster-job:
	uv run dagster job execute -m lovdata_pipeline -j lovdata_processing_job

# Run with limited files for testing
dagster-test:
	MAX_FILES=10 PARSER_MAX_TOKENS=6800 uv run dagster asset materialize -m lovdata_pipeline --select "lovdata_sync,changed_legal_documents,parsed_legal_chunks"

# Run with medium batch
dagster-batch:
	MAX_FILES=100 PARSER_MAX_TOKENS=6800 uv run dagster job execute -m lovdata_pipeline -j lovdata_processing_job

# Sync datasets only (uses LOVDATA_DATASET_FILTER from .env)
dagster-sync:
	uv run dagster asset materialize -m lovdata_pipeline --select "lovdata_sync"

# Sync all datasets (override filter)
dagster-sync-all:
	LOVDATA_DATASET_FILTER="" uv run dagster asset materialize -m lovdata_pipeline --select "lovdata_sync"

docker-build:
	docker-compose build

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f

secrets: .secrets.baseline
	uv run detect-secrets scan --baseline .secrets.baseline

.secrets.baseline:
	uv run detect-secrets scan > .secrets.baseline

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .coverage htmlcov/ dist/ build/

check-tools:
	@echo "🔍 Checking required tools..."
	@echo ""
	@printf "%-20s" "uv:"; \
	if command -v uv &> /dev/null; then \
		echo "✅ $(shell uv --version)"; \
	else \
		echo "❌ Not installed - https://docs.astral.sh/uv/getting-started/installation/"; \
	fi
	@printf "%-20s" "git:"; \
	if command -v git &> /dev/null; then \
		echo "✅ $(shell git --version)"; \
	else \
		echo "❌ Not installed"; \
	fi
	@printf "%-20s" "docker:"; \
	if command -v docker &> /dev/null; then \
		echo "✅ $(shell docker --version)"; \
	else \
		echo "❌ Not installed - https://docs.docker.com/get-docker/"; \
	fi
	@printf "%-20s" "GitHub CLI:"; \
	if command -v gh &> /dev/null; then \
		echo "✅ $(shell gh --version | head -n1)"; \
	else \
		echo "❌ Not installed - https://cli.github.com/"; \
	fi
	@printf "%-20s" "prek:"; \
	if command -v prek &> /dev/null; then \
		echo "✅ $(shell prek --version)"; \
	else \
		echo "⚠️  Not installed - Run: uvx prek install"; \
	fi
	@echo ""
	@echo "💡 Install missing tools using the links above"

.check-gh:
	@command -v gh &> /dev/null || (echo "❌ GitHub CLI (gh) not found. Install it from: https://cli.github.com/" && exit 1)

github-create: .check-gh
	@if [ ! -d .git ]; then \
		echo "📁 Initializing git repository..."; \
		git init; \
		git add .; \
		git commit -m "Initial commit from python_template"; \
	fi
	@echo "🚀 Creating GitHub repository martgra/lovdata-pipeline..."
	@gh repo create martgra/lovdata-pipeline --public --source=. --remote=origin
	@echo "✅ Repository created at: https://github.com/martgra/lovdata-pipeline"
	@echo ""
	@echo "Next: Run 'make github-push' to push your code"

github-push: .check-gh
	@if ! git remote get-url origin &> /dev/null; then \
		echo "❌ No remote 'origin' found. Run 'make github-create' first"; \
		exit 1; \
	fi
	@git push -u origin main || git push -u origin master
	@echo "✅ Code pushed to GitHub"
	@echo "🔗 View at: https://github.com/martgra/lovdata-pipeline"
