# Quick Reference - Lovdata Pipeline

## Installation

```bash
# Clone repository
git clone https://github.com/martgra/lovdata-pipeline.git
cd lovdata-pipeline

# Install dependencies
make install
# or: uv sync
```

## Basic Usage

### Process Documents

```bash
# Run complete pipeline (processes changed files)
uv run python -m lovdata_pipeline process

# Force reprocess all files
uv run python -m lovdata_pipeline process --force

# Use JSONL storage instead of ChromaDB
uv run python -m lovdata_pipeline process --storage jsonl

# Test with first 10 files only
uv run python -m lovdata_pipeline process --limit 10

# Combine options
uv run python -m lovdata_pipeline process -s jsonl -l 5 -f

# With custom options
uv run python -m lovdata_pipeline process \
  --data-dir /custom/path \
  --dataset gjeldende-lover \
  --chunk-max-tokens 4000 \
  --embedding-model text-embedding-3-small \
  --chroma-path /custom/chroma

# Process specific dataset
uv run python -m lovdata_pipeline process --dataset gjeldende-lover

# Process all available datasets
uv run python -m lovdata_pipeline process --dataset "*"
```

### Migrate Between Storage Types

```bash
# Backup ChromaDB to JSONL files
uv run python -m lovdata_pipeline migrate --source chroma --target jsonl

# Restore JSONL to ChromaDB
uv run python -m lovdata_pipeline migrate --source jsonl --target chroma

# Short form
uv run python -m lovdata_pipeline migrate -s chroma -t jsonl

# Custom paths
uv run python -m lovdata_pipeline migrate -s chroma -t jsonl \
  --jsonl-path ./backup \
  --batch-size 500
```

### Check Status

```bash
# View pipeline statistics
uv run python -m lovdata_pipeline status

# With custom data directory
uv run python -m lovdata_pipeline status --data-dir /custom/path
```

## CLI Options

### `process` Command

| Option               | Short | Default                  | Description                                                               |
| -------------------- | ----- | ------------------------ | ------------------------------------------------------------------------- |
| `--force`            | `-f`  | `false`                  | Reprocess all files (ignore state)                                        |
| `--storage`          | `-s`  | `chroma`                 | Storage type: `chroma` or `jsonl`                                         |
| `--limit`            | `-l`  | `None`                   | Limit number of files to process (for testing)                            |
| `--data-dir`         |       | `./data`                 | Data directory path                                                       |
| `--dataset-filter`   |       | `gjeldende`              | Dataset: `gjeldende`, `gjeldende-lover`, `gjeldende-sentrale-forskrifter` |
| `--chunk-max-tokens` |       | `6800`                   | Maximum tokens per chunk                                                  |
| `--embedding-model`  |       | `text-embedding-3-large` | OpenAI embedding model                                                    |
| `--chroma-path`      |       | `./data/chroma`          | ChromaDB storage path                                                     |

### `migrate` Command

| Option          | Short | Default       | Description                         |
| --------------- | ----- | ------------- | ----------------------------------- |
| `--source`      | `-s`  | _(required)_  | Source storage: `chroma` or `jsonl` |
| `--target`      | `-t`  | _(required)_  | Target storage: `chroma` or `jsonl` |
| `--data-dir`    |       | `./data`      | Data directory path                 |
| `--chroma-path` |       | Uses settings | ChromaDB path (if custom)           |
| `--jsonl-path`  |       | Uses settings | JSONL storage path (if custom)      |
| `--batch-size`  |       | `1000`        | Batch size for migration            |

### `status` Command

| Option       | Short | Default  | Description         |
| ------------ | ----- | -------- | ------------------- |
| `--data-dir` |       | `./data` | Data directory path |

## Configuration

### Environment Variables

Create `.env` file:

```bash
# Required
OPENAI_API_KEY=sk-...

# Optional (defaults shown)
DATA_DIR=./data
STORAGE_TYPE=chroma          # or 'jsonl'
LIMIT=                       # or integer (e.g., 10)
CHUNK_MAX_TOKENS=6800
EMBEDDING_MODEL=text-embedding-3-large
CHROMA_PATH=./data/chroma
```

### Dataset Filters

| Filter                           | Description                         | Size  |
| -------------------------------- | ----------------------------------- | ----- |
| `gjeldende`                      | All laws + regulations              | ~10GB |
| `gjeldende-lover`                | Laws only (recommended for testing) | ~2GB  |
| `gjeldende-sentrale-forskrifter` | Regulations only                    | ~8GB  |

## Make Commands

```bash
# Installation
make install         # Install dependencies (frozen)
make update-deps     # Update dependencies

# Running
make process         # Run pipeline
make status          # Show status

# Testing
make test            # Run all tests

# Code Quality
make lint            # Run linter (ruff)
make format          # Format code with ruff

# Utilities
make clean           # Remove cache files
make secrets         # Scan for secrets
make check-tools     # Check if required tools are installed

# GitHub (requires gh CLI)
make github-create   # Create GitHub repository
make github-push     # Push to GitHub
```

## File Structure

```
lovdata-pipeline/
├── data/
│   ├── pipeline_state.json      # Processing state
│   ├── state.json               # Lovlig state (file metadata)
│   ├── raw/                     # Downloaded archives
│   ├── extracted/               # Extracted XML files
│   │   └── gjeldende-lover/
│   └── chroma/                  # Vector database
│       └── chroma.sqlite3
│
├── lovdata_pipeline/
│   ├── cli.py                   # CLI commands
│   ├── pipeline.py              # Atomic processing logic
│   ├── state.py                 # State tracking
│   ├── lovlig.py                # Lovlig wrapper
│   ├── config/
│   │   └── settings.py          # Settings (for programmatic use)
│   ├── domain/                  # Business logic
│   │   ├── models.py
│   │   ├── parsers/
│   │   └── splitters/
│   └── infrastructure/          # External systems
│       ├── chroma_vector_store.py
│       └── jsonl_vector_store.py
│
└── tests/
    ├── unit/
    └── integration/
```

## Common Tasks

### First-Time Setup

```bash
# 1. Clone and install
git clone https://github.com/martgra/lovdata-pipeline.git
cd lovdata-pipeline
make install

# 2. Configure
echo "OPENAI_API_KEY=sk-..." > .env

# 3. Test with small dataset (laws only)
uv run python -m lovdata_pipeline process --dataset gjeldende-lover

# 4. Scale to full dataset (all laws + regulations)
uv run python -m lovdata_pipeline process --dataset gjeldende

# 5. Or process all available datasets
uv run python -m lovdata_pipeline process --dataset "*"
```

### Incremental Updates

```bash
# Initial processing
uv run python -m lovdata_pipeline process

# Later: only processes changed files
uv run python -m lovdata_pipeline process
```

### Reset and Reprocess

```bash
# Delete state and vectors
rm -rf data/pipeline_state.json data/chroma/

# Reprocess everything
uv run python -m lovdata_pipeline process --force
```

### Development Workflow

```bash
# Install with dev dependencies
make install-dev

# Make changes
# ... edit code ...

# Test
make test

# Lint and format
make lint
make format

# Run pipeline
uv run python -m lovdata_pipeline process
```

## Troubleshooting

### Check Logs

Pipeline outputs detailed progress:

```
INFO Processing 156 changed files...
INFO [1/156] nl-18840614-003: 42 chunks → embedded → indexed (8 vectors)
INFO [2/156] nl-18840614-004: 18 chunks → embedded → indexed (3 vectors)
...
```

### Inspect State

```bash
# View processing state
cat data/pipeline_state.json | jq '.'

# View lovlig state
cat data/state.json | jq '.files[] | select(.status == "modified")'

# Count processed documents
jq '.processed | length' data/pipeline_state.json
```

### Common Errors

| Error                    | Solution                                        |
| ------------------------ | ----------------------------------------------- |
| `OPENAI_API_KEY not set` | Set in `.env` or export `OPENAI_API_KEY=sk-...` |
| `Rate limit exceeded`    | Wait and retry (state persists)                 |
| `database is locked`     | Kill other pipeline processes                   |
| `Out of memory`          | Use smaller dataset or increase RAM             |
| Invalid JSON in state    | Delete `data/pipeline_state.json` and reprocess |

### Debug Mode

Enable verbose logging:

```python
# In lovdata_pipeline/cli.py
logging.basicConfig(level=logging.DEBUG, ...)
```

## Testing

```bash
# Run all tests
uv run pytest tests/

# Run specific test file
uv run pytest tests/unit/state_test.py

# Run specific test
uv run pytest tests/unit/state_test.py::test_mark_processed

# With coverage
uv run pytest tests/ --cov=lovdata_pipeline --cov-report=html

# View coverage
open htmlcov/index.html
```

## Performance

### Approximate Times

| Dataset           | Files   | Time (first run) | Subsequent |
| ----------------- | ------- | ---------------- | ---------- |
| `gjeldende-lover` | ~3,000  | ~30 min          | ~1-2 min   |
| `gjeldende`       | ~15,000 | ~3 hours         | ~5-10 min  |

_Times vary based on network, CPU, and OpenAI rate limits._

### Cost Estimate

| Dataset           | Chunks  | Tokens | Cost (OpenAI) |
| ----------------- | ------- | ------ | ------------- |
| `gjeldende-lover` | ~10,000 | ~68M   | ~$9           |
| `gjeldende`       | ~50,000 | ~340M  | ~$45          |

_Using text-embedding-3-large at $0.13/1M tokens._

## Resources

- **[User Guide](USER_GUIDE.md)** - Complete usage guide
- **[Developer Guide](DEVELOPER_GUIDE.md)** - Architecture and extending
- **[Functional Requirements](FUNCTIONAL_REQUIREMENTS.md)** - Specification
- **[GitHub Repository](https://github.com/martgra/lovdata-pipeline)** - Source code
