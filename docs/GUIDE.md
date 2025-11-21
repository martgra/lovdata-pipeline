# Lovdata Pipeline Guide

Complete guide for installing, configuring, and using the Lovdata legal document processing pipeline.

## Table of Contents

- [Quick Start](#quick-start)
- [Installation](#installation)
  - [Prerequisites](#prerequisites)
  - [Install Pipeline](#install-pipeline)
  - [Install lovlig (Data Source)](#install-lovlig-data-source)
- [Configuration](#configuration)
  - [Environment Variables](#environment-variables)
  - [Storage Options](#storage-options)
- [Usage](#usage)
  - [Basic Commands](#basic-commands)
  - [CLI Reference](#cli-reference)
  - [Processing Behavior](#processing-behavior)
- [File Structure](#file-structure)
  - [Data Files](#data-files)
- [Monitoring](#monitoring)
  - [Processing Output](#processing-output)
  - [State Files](#state-files)
- [Migration Between Storage Types](#migration-between-storage-types)
- [Advanced Usage](#advanced-usage)
  - [Custom Chunk Size](#custom-chunk-size)
  - [Filter by Dataset](#filter-by-dataset)
  - [Batch Processing](#batch-processing)
  - [State Management](#state-management)
- [Troubleshooting](#troubleshooting)
  - [Processing Failures](#processing-failures)
  - [API Rate Limits](#api-rate-limits)
  - [Missing Dependencies](#missing-dependencies)
  - [Data Issues](#data-issues)
- [Performance](#performance)
  - [Costs](#costs)
  - [Processing Speed](#processing-speed)
  - [Optimization Tips](#optimization-tips)
- [Testing](#testing)
- [Common Tasks](#common-tasks)
- [Support](#support)

---

## Quick Start

```bash
# Install
make install

# Configure (set OpenAI API key)
export OPENAI_API_KEY="sk-..."

# Run pipeline
uv run lg process --storage jsonl --limit 10
```

> **Tip:** Use `--limit 10` when testing to process only a small batch of files and verify your setup works correctly.

## Installation

### Prerequisites

- **Python 3.11+**
- **OpenAI API key** (for embeddings)
- **uv** package manager (auto-installed by `make install`)

> **Note:** ChromaDB Python client is automatically installed as a dependency. No separate server installation is required for local usage.

### Install Pipeline

```bash
# Clone repository
git clone https://github.com/martgra/lovdata-pipeline.git
cd lovdata-pipeline

# Install dependencies
make install

# Verify installation
uv run lg --help
```

### Install lovlig (Data Source)

The pipeline uses `lovlig` to download/sync Lovdata files:

```bash
# Install lovlig
gh repo clone martgra/lovlig
cd lovlig
cargo build --release

# Sync data (downloads ~1GB)
./target/release/lovlig sync --output-dir ../lovdata-pipeline/data
```

---

## Configuration

### Environment Variables

> **Important:** You must set `OPENAI_API_KEY` to use the pipeline. Get your API key from [platform.openai.com](https://platform.openai.com).

Create `.env` file:

```bash
# Required
OPENAI_API_KEY=sk-...

# Optional
DATA_DIR=./data                          # Data directory
DATASET_FILTER=gjeldende-lover           # Dataset to process
OPENAI_EMBEDDING_MODEL=text-embedding-3-large
CHROMA_STORAGE_PATH=./data/chroma        # ChromaDB storage
JSONL_STORAGE_PATH=./data/jsonl_chunks   # JSONL storage
TARGET_TOKENS=768                        # Chunk size
```

### Storage Options

**JSONL (Recommended for most users):**

- Simple file-based storage - one `.jsonl` file per document
- Easy to backup, version control, and inspect
- No external dependencies
- Portable and human-readable

**ChromaDB (For advanced users):**

- Full-featured vector database with built-in search capabilities
- Better for large-scale operations (10K+ documents)
- Embedded mode (default) - no separate server needed
- Optional: Can connect to remote ChromaDB server for production deployments

```bash
# Use JSONL (default)
uv run lg process --storage jsonl

# Use ChromaDB
uv run lg process --storage chroma
```

## Usage

### Basic Commands

```bash
# Process all files
uv run lg process --storage jsonl

# Process with limit (for testing)
uv run lg process --storage jsonl --limit 10

# Force reprocess all files
uv run lg process --storage jsonl --force

# Check status
uv run lg status

# Search chunks (ChromaDB only)
uv run lg search "arbeidsrett" --limit 5

# Migrate between storage types
uv run lg migrate --source chroma --target jsonl
```

> **Warning:** The `--force` flag will reprocess all files, potentially incurring API costs. Use `--limit` to test with a small batch first.

### CLI Reference

**`lg process`** - Run the processing pipeline

```bash
Options:
  --storage TEXT      Storage backend: 'chroma' or 'jsonl' [default: jsonl]
  --limit INTEGER     Limit number of files to process
  --force            Force reprocess all files
  --data-dir PATH    Data directory [default: ./data]
  --dataset TEXT     Dataset filter [default: gjeldende-lover]
```

**`lg status`** - Show pipeline statistics

```bash
uv run lg status --data-dir ./data
```

**`lg search`** - Search documents (ChromaDB only)

```bash
uv run lg search "arbeidsrett" --limit 5
```

**`lg migrate`** - Migrate between storage types

```bash
uv run lg migrate --source chroma --target jsonl
```

### Processing Behavior

> **Note:** Understanding the pipeline's behavior helps you manage data efficiently and avoid unexpected costs.

The pipeline is **incremental** and **atomic**:

1. **Incremental**: Only processes changed/new files

   - Uses file hashes to detect changes
   - Tracks state in `data/pipeline_state.json`
   - Automatically removes old chunks when files change

2. **Atomic**: Completes each file fully before moving to next

   - All chunks for a file are written together
   - If processing fails, file is marked as failed
   - Next run will retry failed files

3. **Automatic cleanup**: When files are removed or modified:
   - Old chunks are automatically deleted
   - State is updated to reflect changes
   - No manual cleanup needed

## File Structure

```
data/
├── extracted/              # XML files from lovlig
│   └── gjeldende-lover/
│       └── nl/
│           └── *.xml
├── jsonl_chunks/           # Processed chunks (JSONL)
│   └── *.jsonl
├── chroma/                 # ChromaDB storage (if using)
├── state.json             # lovlig state (file hashes)
└── pipeline_state.json    # Processing state
```

### Data Files

**`extracted/`** - Source XML files from Lovdata

- Downloaded by `lovlig sync`
- Organized by dataset and doc ID

**`jsonl_chunks/`** - Processed chunks (JSONL storage)

- One `.jsonl` file per source document
- Contains all chunks with embeddings and metadata
- File named by source document hash

**`state.json`** - lovlig state tracking

- File hashes for change detection
- Updated by `lovlig sync`

**`pipeline_state.json`** - Processing state

- Tracks which files have been processed
- Records file hashes for change detection
- Lists failed files with error messages

## Monitoring

### Processing Output

```
═══ Lovdata Pipeline ═══
Dataset: gjeldende-lover.tar.bz2
Storage: jsonl
Limit: 10 files (testing mode)

═══ Syncing datasets ═══
gjeldende-lover.tar.bz2                     Up to date

═══ Identifying files ═══
Found: 3 changed files

═══ Processing documents ═══
█████████████████ 3/3 [00:15<00:00]

═══ Summary ═══
✓ Processed: 3 documents
✗ Failed: 0 documents
```

### State Files

**Check processing state:**

```bash
# View processed files
cat data/pipeline_state.json | jq '.processed | keys'

# View failed files
cat data/pipeline_state.json | jq '.failed'

# Count chunks
find data/jsonl_chunks -name "*.jsonl" | wc -l
```

**Check lovlig state:**

```bash
# View tracked files
cat data/state.json | jq '.files | length'

# View file changes
cat data/state.json | jq '.files | to_entries[] | select(.value.status != "unmodified")'
```

## Migration Between Storage Types

Migrate chunks between ChromaDB and JSONL storage backends. The migration handles metadata format differences automatically (e.g., `cross_refs` is stored as a comma-separated string in ChromaDB but as a list in JSONL).

```bash
# ChromaDB → JSONL
uv run lg migrate --source chroma --target jsonl

# JSONL → ChromaDB
uv run lg migrate --source jsonl --target chroma

# Custom paths
uv run lg migrate -s chroma -t jsonl --jsonl-path ./backup

# Adjust batch size for large migrations
uv run lg migrate -s jsonl -t chroma --batch-size 500
```

## Advanced Usage

### Custom Chunk Size

```bash
export TARGET_TOKENS=512  # Smaller chunks, more embeddings
export TARGET_TOKENS=1024 # Larger chunks, fewer embeddings
```

### Filter by Dataset

```bash
# Process only current laws
export DATASET_FILTER=gjeldende-lover

# Process only regulations
export DATASET_FILTER=forskrifter
```

### Batch Processing

```bash
# Test with small batch
uv run lg process --storage jsonl --limit 10

# Process 100 files at a time
uv run lg process --storage jsonl --limit 100
```

### State Management

```bash
# View processing statistics
uv run lg status

# Reset state (reprocess all files)
rm data/pipeline_state.json

# Simulate file changes (for testing)
uv run python scripts/tamper.py clear-state --count 10
```

## Troubleshooting

### Processing Failures

**Problem:** Files fail to process

**Solutions:**

1. Check error messages in `data/pipeline_state.json`:

   ```bash
   cat data/pipeline_state.json | jq '.failed'
   ```

2. Re-run pipeline (will retry failed files):

   ```bash
   uv run lg process --storage jsonl
   ```

3. Force reprocess specific files:
   - Remove from `pipeline_state.json`
   - Run pipeline again

### API Rate Limits

**Problem:** OpenAI rate limit errors

**Solutions:**

1. Use `--limit` to process fewer files:

   ```bash
   uv run lg process --storage jsonl --limit 50
   ```

2. Reduce chunk size to generate fewer embeddings:

   ```bash
   export TARGET_TOKENS=512
   ```

3. Wait and retry (rate limits reset automatically)

### Missing Dependencies

**Problem:** `uv` or `lovlig` not found

**Solutions:**

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Build lovlig
cd ../lovlig
cargo build --release
```

### Data Issues

**Problem:** No files found to process

**Solutions:**

1. Sync data with lovlig:

   ```bash
   cd ../lovlig
   ./target/release/lovlig sync --output-dir ../lovdata-pipeline/data
   ```

2. Check dataset filter:

   ```bash
   export DATASET_FILTER=gjeldende-lover
   ```

3. Verify data directory structure:
   ```bash
   ls -la data/extracted/
   ```

**Problem:** Stale chunks or incorrect state

**Solution:**

> **Warning:** This will delete all processing state and chunks. You'll need to reprocess everything, which will incur API costs.

```bash
# Remove state files
rm data/pipeline_state.json

# Optionally remove chunks
rm -rf data/jsonl_chunks/*

# Reprocess
uv run lg process --storage jsonl
```

---

## Performance

### Costs

**OpenAI Embedding API** (text-embedding-3-large):

- ~$0.13 per 1M tokens
- Average document: 200-500 tokens per chunk
- 1000 documents ≈ $0.05-0.15

**Storage:**

- JSONL: ~1-2MB per 1000 chunks
- ChromaDB: ~5-10MB per 1000 chunks (includes index)

### Processing Speed

- **Chunking:** ~10-50 files/second (CPU bound)
- **Embedding:** ~5-10 chunks/second (API rate limited)
- **Storage:** ~100-500 chunks/second (I/O bound)

**Bottleneck:** OpenAI API rate limits (3,500 requests/minute for tier 1)

### Optimization Tips

1. **Use JSONL storage** - Faster, simpler, more reliable
2. **Process in batches** - Use `--limit` for testing
3. **Reduce chunk size** - Lower `TARGET_TOKENS` for fewer embeddings
4. **Monitor rate limits** - OpenAI API has request/minute limits

## Testing

### Run Tests

```bash
# All tests
make test

# Unit tests only
uv run pytest tests/unit/

# Integration tests
uv run pytest tests/integration/

# Specific test file
uv run pytest tests/unit/test_chunking_service.py
```

### Test Coverage

```bash
# Generate coverage report
make coverage

# View HTML report
open htmlcov/index.html
```

## Common Tasks

### Add New Documents

```bash
# 1. Sync with lovlig
cd ../lovlig
./target/release/lovlig sync --output-dir ../lovdata-pipeline/data

# 2. Process new files (automatically detected)
cd ../lovdata-pipeline
uv run lg process --storage jsonl
```

### Reprocess Changed Documents

```bash
# lovlig detects changes automatically
uv run lg process --storage jsonl
```

### Clean Up and Start Fresh

```bash
# Remove all processed data
rm -rf data/jsonl_chunks/*
rm data/pipeline_state.json

# Reprocess everything
uv run lg process --storage jsonl
```

## Support

- **Issues:** https://github.com/martgra/lovdata-pipeline/issues
- **Documentation:** https://github.com/martgra/lovdata-pipeline/tree/main/docs
- **lovlig:** https://github.com/martgra/lovlig
