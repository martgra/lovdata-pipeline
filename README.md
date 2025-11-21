# lovdata-pipeline

![CI](https://github.com/martgra/lovdata-pipeline/actions/workflows/ci.yaml/badge.svg?branch=main)
![Python](https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white)
[![Copier](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/copier-org/copier/master/img/badge/badge-grayscale-inverted-border-orange.json)](https://github.com/copier-org/copier)

A simple Python pipeline for processing Norwegian legal documents from Lovdata into a searchable vector database.

![Demo](docs/assets/demo.gif)

## Quick Start

```bash
# Install dependencies
make install

# Run pipeline (process all changed files)
uv run lg process --storage jsonl
```

One command processes all changed files. Each file completes fully (parse → chunk → embed → index) before moving to the next. Simple JSON state tracking.

## Documentation

- **[Guide](docs/GUIDE.md)** - Complete user manual (installation, configuration, usage, troubleshooting)
- **[Development](docs/DEVELOPMENT.md)** - Developer reference (architecture, extending, testing, contributing)

## What It Does

Processes Norwegian legal documents into searchable vectors:

1. **Sync** - Download from Lovdata (via lovlig library)
2. **Parse & Chunk** - Extract and split articles into semantic chunks
3. **Embed** - Generate vectors via OpenAI API
4. **Index** - Store in JSONL files or ChromaDB

**Atomic Processing:** Each file completes all steps before the next file starts. If processing fails, the file is marked as failed and retried on the next run.

## Architecture design with dependency injection and protocol-based interfaces for extensibility. See [DEVELOPMENT.md](docs/DEVELOPMENT.md) for architecture details.

## Key Features

**Processing:**

- Atomic per-file execution (all-or-nothing)
- Automatic change detection and cleanup
- Simple JSON state tracking
- Single-command operation

**Storage:**

- JSONL files (simple, portable) or ChromaDB (production-ready)
- Automatic migration between storage types

**Development:**

- Quality tools (Ruff, Pylint, pre-commit hooks)
- Full test coverage with pytest
- Dev container for reproducible environment

## Requirements

- Python ≥ 3.11
- OpenAI API key (for embeddings)
- ChromaDB (auto-installed)

## License

MIT License
