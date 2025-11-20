# lovdata-pipeline

![CI](https://github.com/martgra/lovdata-pipeline/actions/workflows/ci.yaml/badge.svg?branch=main)
![Python](https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white)
[![Copier](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/copier-org/copier/master/img/badge/badge-grayscale-inverted-border-orange.json)](https://github.com/copier-org/copier)

A simple Python pipeline for processing Norwegian legal documents from Lovdata into a searchable vector database.

## Quick Start

```bash
# Install dependencies
make install

# Run pipeline
uv run python -m lovdata_pipeline process
```

One command. Atomic per-file processing. Simple state tracking.

## Documentation

### For Users

- **[User Guide](docs/USER_GUIDE.md)** - Installation, usage, configuration, troubleshooting
- **[Quick Reference](docs/QUICK_REFERENCE.md)** - Command cheat sheet

### For Developers

- **[Developer Guide](docs/DEVELOPER_GUIDE.md)** - Architecture, extending, testing, contributing
- **[Functional Requirements](docs/FUNCTIONAL_REQUIREMENTS.md)** - Specification that all changes must satisfy

## What It Does

For each file:

1. **Sync** - Download from Lovdata (via lovlig library)
2. **Parse & Chunk** - Extract and split articles (LovdataChunker)
3. **Embed** - Generate embeddings via OpenAI (EmbeddingService)
4. **Index** - Store in ChromaDB (VectorStore)

Atomic processing: each file completes fully before moving to the next.

### Architecture

The pipeline uses a **service-oriented architecture** with:

- **Dependency Injection** - Services wired through factory pattern
- **Protocol Interfaces** - Extensible via `EmbeddingProvider` and `VectorStoreRepository` protocols
- **Domain Services** - Parsing, chunking, embedding, and file processing
- **Orchestration Layer** - `PipelineOrchestrator` coordinates the workflow

## Key Features

- **Atomic processing** - Complete each file before moving to next
- **Simple state** - JSON file tracks processed/failed documents
- **Change detection** - Uses lovlig library for file changes
- **Automatic cleanup** - Removes vectors for deleted/modified files
- **Single command** - No stages, no complex orchestration
- **Quality tools** - Ruff, Pylint, Prek git hooks
- **Dev container** - Reproducible environment

## Requirements

- Python ≥ 3.11
- OpenAI API key (for embeddings)
- ChromaDB (auto-installed)

## License

MIT License
