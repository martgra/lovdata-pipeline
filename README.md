# lovdata-pipeline

![CI](https://github.com/martgra/lovdata-pipeline/actions/workflows/ci.yaml/badge.svg?branch=main)
![Python](https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white)
[![Copier](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/copier-org/copier/master/img/badge/badge-grayscale-inverted-border-orange.json)](https://github.com/copier-org/copier)

A Python pipeline for processing Norwegian legal documents from Lovdata into a searchable vector database.

## Quick Start

```bash
# Install dependencies
make install

# Run complete pipeline
make full
```

No servers, no orchestration - just Python commands.

## Documentation

### For Users

- **[User Guide](docs/USER_GUIDE.md)** - Installation, usage, configuration, troubleshooting

### For Developers

- **[Developer Guide](docs/DEVELOPER_GUIDE.md)** - Architecture, extending, testing, contributing
- **[Functional Requirements](docs/FUNCTIONAL_REQUIREMENTS.md)** - Specification that all changes must satisfy

### Reference

- **[Quick Reference](docs/QUICK_REFERENCE.md)** - Command cheat sheet
- **[Incremental Updates](docs/INCREMENTAL_UPDATES.md)** - How change detection works

## What It Does

1. **Sync** - Downloads legal documents from Lovdata
2. **Chunk** - Parses XML into searchable chunks
3. **Embed** - Generates embeddings via OpenAI
4. **Index** - Stores vectors in ChromaDB

Only processes changed files. Resumes from failures.

## Key Features

- **Incremental processing** - Only handles new/modified files
- **Memory efficient** - Streams large datasets
- **Simple CLI** - No servers or orchestration
- **Quality tools** - Ruff, Pylint, Prek git hooks
- **Dev container** - Reproducible environment

## Requirements

- Python ≥ 3.11
- OpenAI API key (for embeddings)
- ChromaDB (for vector storage)

## License

MIT License
