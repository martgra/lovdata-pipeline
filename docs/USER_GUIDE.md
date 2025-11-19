# User Guide

Complete guide for installing, configuring, and using the Lovdata pipeline.

## Table of Contents

- [Installation](#installation)
- [Configuration](#configuration)
- [Basic Usage](#basic-usage)
- [Pipeline Steps](#pipeline-steps)
- [Monitoring](#monitoring)
- [Troubleshooting](#troubleshooting)
- [Scheduled Execution](#scheduled-execution)

---

## Installation

### Prerequisites

- Python ≥ 3.11
- OpenAI API key
- ChromaDB (optional: auto-installs with dependencies)

### Install Dependencies

```bash
# Clone repository
git clone https://github.com/martgra/lovdata-pipeline.git
cd lovdata-pipeline

# Install with uv
make install
# or: uv sync
```

### Verify Installation

```bash
python -m lovdata_pipeline --help
```

---

## Configuration

Create a `.env` file in the project root:

```bash
# Required: Dataset sync
# Filter patterns:
#   'gjeldende' - Both laws and regulations (gjeldende-lover + gjeldende-sentrale-forskrifter)
#   'gjeldende-lover' - Only laws (~1/5 size, recommended for testing)
#   'gjeldende-sentrale-forskrifter' - Only central regulations
LOVDATA_DATASET_FILTER=gjeldende
LOVDATA_RAW_DATA_DIR=./data/raw
LOVDATA_EXTRACTED_DATA_DIR=./data/extracted
LOVDATA_STATE_FILE=./data/state.json
LOVDATA_MAX_DOWNLOAD_CONCURRENCY=4

# Required: Embedding
LOVDATA_OPENAI_API_KEY=sk-...

# Optional: Chunking (defaults shown)
LOVDATA_CHUNK_MAX_TOKENS=6800
LOVDATA_CHUNK_OUTPUT_PATH=./data/chunks/legal_chunks.jsonl

# Optional: Embedding (defaults shown)
LOVDATA_EMBEDDING_MODEL=text-embedding-3-large
LOVDATA_EMBEDDING_BATCH_SIZE=100
LOVDATA_ENRICHED_DATA_DIR=./data/enriched

# Optional: ChromaDB (defaults shown)
# Mode: 'memory' (ephemeral), 'persistent' (local disk), or 'client' (remote server)
LOVDATA_CHROMA_MODE=persistent
LOVDATA_CHROMA_HOST=localhost  # For 'client' mode
LOVDATA_CHROMA_PORT=8000       # For 'client' mode
LOVDATA_CHROMA_PERSIST_DIRECTORY=./data/chroma  # For 'persistent' mode
LOVDATA_CHROMA_COLLECTION=legal_docs
LOVDATA_MANIFEST_PATH=./data/manifest.json
```

**Tip:** Copy `.env.example` as a starting point.

---

## ChromaDB Setup

Choose one of three deployment modes:

### Option 1: Persistent (Default - Recommended)

Stores vectors locally on disk. Data persists across restarts.

```bash
# In .env
LOVDATA_CHROMA_MODE=persistent
LOVDATA_CHROMA_PERSIST_DIRECTORY=./data/chroma

# Run pipeline
make full
```

**Pros:** Simple, no server needed, data persists  
**Cons:** Local only, no remote access

### Option 2: In-Memory (Fast, Ephemeral)

Stores vectors in memory. **Data lost on restart.**

```bash
# In .env
LOVDATA_CHROMA_MODE=memory

# Run pipeline
make full
```

**Pros:** Fast, no disk I/O  
**Cons:** Data lost on restart, RAM usage

### Option 3: Client/Server (Remote)

Connect to a remote ChromaDB server.

```bash
# Start ChromaDB server (Docker)
docker compose up -d

# In .env
LOVDATA_CHROMA_MODE=client
LOVDATA_CHROMA_HOST=localhost
LOVDATA_CHROMA_PORT=8000

# Run pipeline
make full
```

**Pros:** Remote access, scalable, persistent  
**Cons:** Requires server setup

---

## Basic Usage

### Run Complete Pipeline

Processes all steps: sync → chunk → embed → index

```bash
make full
# or: python -m lovdata_pipeline full
```

### Run Individual Steps

```bash
# 1. Download and extract datasets
make sync
# or: python -m lovdata_pipeline sync

# 2. Parse XML and create chunks
make chunk
# or: python -m lovdata_pipeline chunk

# 3. Generate embeddings
make embed
# or: python -m lovdata_pipeline embed

# 4. Index in vector database
make index
# or: python -m lovdata_pipeline index

# 5. Clean up orphaned vectors (optional)
make reconcile
# or: python -m lovdata_pipeline reconcile
```

---

## Pipeline Steps

### 1. Sync

Downloads legal documents from Lovdata and extracts XML files.

```bash
python -m lovdata_pipeline sync
```

**What it does:**

- Downloads dataset archives via Lovdata API
- Extracts XML files to `data/extracted/`
- Updates `data/state.json` with file metadata
- Detects added, modified, and removed files

**Force re-download:**

```bash
python -m lovdata_pipeline sync --force-download
```

### 2. Chunk

Parses XML documents and creates text chunks.

```bash
python -m lovdata_pipeline chunk
```

**What it does:**

- Reads XML files from `data/extracted/`
- Parses legal structure (articles, paragraphs)
- Splits into chunks respecting token limits (6800 default)
- Writes to `data/chunks/legal_chunks.jsonl`

**Force reprocess all files:**

```bash
python -m lovdata_pipeline chunk --force-reprocess
```

### 3. Embed

Generates embeddings for chunks using OpenAI.

```bash
python -m lovdata_pipeline embed
```

**What it does:**

- Reads chunks from `data/chunks/`
- Batches API calls to OpenAI (100 chunks/batch)
- Writes enriched chunks with embeddings to `data/enriched/`

**Force re-embed all chunks:**

```bash
python -m lovdata_pipeline embed --force-reembed
```

**Cost estimate:** ~$0.13 per 1M tokens with `text-embedding-3-large`

### 4. Index

Stores embeddings in ChromaDB vector database.

```bash
python -m lovdata_pipeline index
```

**What it does:**

- Reads enriched chunks from `data/enriched/`
- Upserts vectors to ChromaDB
- Creates searchable index with metadata

**Note:** ChromaDB must be running (HTTP mode) or uses local storage.

### 5. Reconcile (Optional)

Removes "ghost" documents from the index that no longer exist in source data.

```bash
python -m lovdata_pipeline reconcile
```

**When to use:** After removing datasets or manual index cleanup.

---

## Monitoring

### Check Processing Status

```bash
# Count source XML files
find data/extracted -name "*.xml" | wc -l

# Count processed files
cat data/processed_files.json | jq 'to_entries | length'

# Count chunks
wc -l data/chunks/legal_chunks.jsonl

# Count enriched chunks
wc -l data/enriched/embedded_chunks.jsonl

# View sync state
cat data/state.json | jq '.files | length'
```

### View State Files

**Sync state:**

```bash
cat data/state.json | jq '.files | to_entries | .[0]'
```

**Processing state:**

```bash
cat data/processed_files.json | jq 'to_entries | .[0]'
```

**Embedding state:**

```bash
cat data/embedded_files.json | jq 'to_entries | .[0]'
```

### Pipeline Statistics

Pipeline outputs statistics after each step:

```
Chunking Statistics:
  Files processed: 2847/2850 (99.89%)
  Total chunks: 142,350
  Average chunks/file: 50.0
  Output size: 234.5 MB
```

---

## Troubleshooting

### Pipeline Fails During Chunk

**Symptom:** XML parse errors or encoding issues

**Solution:**

```bash
# Check logs for specific file
python -m lovdata_pipeline chunk 2>&1 | tee chunk.log
grep ERROR chunk.log

# Skip failed files (they're logged)
# Re-run with force to retry
python -m lovdata_pipeline chunk --force-reprocess
```

### Embedding Step Slow

**Symptom:** Takes >60 minutes

**Causes:**

- OpenAI API rate limits
- Large batch size causing timeouts

**Solutions:**

```bash
# Reduce batch size
export LOVDATA_EMBEDDING_BATCH_SIZE=50

# Use smaller model (faster, cheaper)
export LOVDATA_EMBEDDING_MODEL=text-embedding-3-small
```

### ChromaDB Connection Failed

**Symptom:** `Connection refused` errors

**Solutions:**

**Option 1: Use local storage (default)**

```bash
# No server needed - uses persistent directory
python -m lovdata_pipeline index
```

**Option 2: Start ChromaDB server**

```bash
# In separate terminal
docker run -p 8000:8000 chromadb/chroma

# Then run index
python -m lovdata_pipeline index
```

### Disk Space Issues

**Symptom:** Pipeline fails with "No space left"

**Data sizes (approximate for 3000 documents):**

- Raw archives: 500 MB
- Extracted XML: 1.5 GB
- Chunks: 250 MB
- Enriched chunks: 2 GB
- ChromaDB: 1 GB

**Solutions:**

```bash
# Clean intermediate files
make clean

# Remove archives after extraction
rm -rf data/raw/*.tar.bz2
```

### Re-run from Scratch

```bash
# Delete all data
rm -rf data/

# Run full pipeline
python -m lovdata_pipeline full --force-download --force-reprocess
```

---

## Scheduled Execution

### Daily Updates with Cron

```bash
# Edit crontab
crontab -e

# Add daily run at 2 AM
0 2 * * * cd /path/to/lovdata-pipeline && make full >> logs/pipeline.log 2>&1
```

### GitHub Actions

See `.github/workflows/` for CI/CD examples.

Example workflow for scheduled runs:

```yaml
name: Daily Pipeline

on:
  schedule:
    - cron: "0 2 * * *" # Daily at 2 AM UTC

jobs:
  run-pipeline:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v1
      - run: make install
      - run: make full
        env:
          LOVDATA_OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

### Docker

#### ChromaDB in Docker

```bash
# Start ChromaDB service
docker compose up -d

# Pipeline connects to localhost:8000
make full
```

#### Pipeline in Docker (Optional)

```bash
# Build image
docker build -t lovdata-pipeline .

# Run with mounted data and env file
docker run --rm \
  -v $(pwd)/data:/data \
  --env-file .env \
  lovdata-pipeline \
  uv run python -m lovdata_pipeline full
```

---

## Performance Tips

### Incremental Processing (Default)

Pipeline only processes changed files by default. No flags needed.

### Parallel Processing

Currently processes files sequentially. Parallel processing not yet implemented.

### Memory Usage

Expected peak: ~200 MB for largest XML document. Safe for 1 GB RAM systems.

### Processing Time

Approximate times for 3000 documents:

| Step  | Duration  | Bottleneck             |
| ----- | --------- | ---------------------- |
| Sync  | 5-10 min  | Network, extraction    |
| Chunk | 10-15 min | XML parsing            |
| Embed | 30-60 min | OpenAI API rate limits |
| Index | 5-10 min  | ChromaDB writes        |

**Total:** ~1 hour for full pipeline (first run)  
**Incremental:** ~5-10 minutes for typical updates

---

## Next Steps

- [Developer Guide](DEVELOPER_GUIDE.md) - Extend and customize the pipeline
- [Quick Reference](QUICK_REFERENCE.md) - Command cheat sheet
- [Incremental Updates](INCREMENTAL_UPDATES.md) - How change detection works
