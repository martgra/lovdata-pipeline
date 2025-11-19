# User Guide

Complete guide for installing, configuring, and using the Lovdata pipeline.

## Table of Contents

- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [ChromaDB Setup](#chromadb-setup)
- [Monitoring](#monitoring)
- [Troubleshooting](#troubleshooting)

---

## Installation

### Prerequisites

- Python ≥ 3.11
- OpenAI API key
- ChromaDB (auto-installed with dependencies)

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
uv run python -m lovdata_pipeline --help
```

---

## Configuration

Create a `.env` file in the project root:

```bash
# Required: OpenAI API key for embeddings
OPENAI_API_KEY=sk-...

# Optional: Override defaults
DATA_DIR=./data                           # Data directory (default: ./data)
DATASET_FILTER=gjeldende                  # Dataset filter (default: gjeldende)
CHUNK_MAX_TOKENS=6800                     # Max tokens per chunk (default: 6800)
EMBEDDING_MODEL=text-embedding-3-large    # OpenAI model (default: text-embedding-3-large)
CHROMA_PATH=./data/chroma                 # ChromaDB path (default: ./data/chroma)
```

### Dataset Selection

Choose which Norwegian legal documents to process using the `--dataset` (`-d`) option:

- `gjeldende` - All current laws and regulations (full dataset, ~10GB) **[default]**
- `gjeldende-lover` - Only laws (~2GB, recommended for testing)
- `gjeldende-sentrale-forskrifter` - Only central regulations (~8GB)
- `*` - All available datasets (use quotes in shell)
- Custom patterns supported (e.g., `gjeldende-*`)

**Recommendation:** Start with `gjeldende-lover` for testing, then scale to `gjeldende` for production.

**Examples:**

```bash
# Laws only (recommended for testing)
uv run python -m lovdata_pipeline process --dataset gjeldende-lover

# All laws + regulations
uv run python -m lovdata_pipeline process --dataset gjeldende

# Regulations only
uv run python -m lovdata_pipeline process --dataset gjeldende-sentrale-forskrifter

# All available datasets
uv run python -m lovdata_pipeline process --dataset "*"
```

---

## Usage

### Run Complete Pipeline

Process all documents (or only changed files):

```bash
uv run python -m lovdata_pipeline process
```

This command:

1. Syncs files from Lovdata (detects changes)
2. For each changed/new file:
   - Parses XML into articles
   - Chunks articles into token-sized pieces
   - Generates embeddings via OpenAI
   - Indexes vectors in ChromaDB
3. Cleans up vectors for deleted files

**Force reprocess all files:**

```bash
uv run python -m lovdata_pipeline process --force
```

### Check Status

View pipeline statistics:

```bash
uv run python -m lovdata_pipeline status
```

Shows:

- Number of processed documents
- Number of failed documents
- Total vectors indexed

---

## ChromaDB Setup

The pipeline uses ChromaDB in persistent mode by default, storing vectors locally on disk at `./data/chroma`.

### Configuration

```bash
# In .env
CHROMA_PATH=./data/chroma
```

Data persists across runs. No server required.

**Note:** ChromaDB is automatically installed as a dependency. The pipeline uses the embedded persistent mode, which stores vectors in the local filesystem at the configured path.

---

## Monitoring

### Progress Logging

The pipeline outputs detailed logs:

```
═══ Lovdata Pipeline ═══
INFO Processing 156 changed files...
INFO [1/156] nl-18840614-003: 42 chunks → embedded → indexed (8 vectors)
INFO [2/156] nl-18840614-004: 18 chunks → embedded → indexed (3 vectors)
...
✓ Complete!
  Processed: 156
  Failed: 0
```

### State File

The pipeline maintains `data/pipeline_state.json`:

```json
{
  "processed": {
    "nl-18840614-003": {
      "hash": "abc123...",
      "vectors": ["vec_id_1", "vec_id_2"],
      "timestamp": "2025-11-19T10:30:00Z"
    }
  },
  "failed": {}
}
```

### Data Files

```
data/
├── pipeline_state.json      # Processing state (what's done)
├── state.json               # Lovlig state (file metadata)
├── raw/                     # Downloaded archives (managed by lovlig)
├── extracted/               # Extracted XML files (managed by lovlig)
│   └── gjeldende-lover/
│       └── nl/*.xml
└── chroma/                  # ChromaDB storage
    └── chroma.sqlite3
```

---

## Troubleshooting

### Common Issues

#### 1. OpenAI API Key Error

```
Error: OPENAI_API_KEY not set
```

**Solution:** Set environment variable:

```bash
export OPENAI_API_KEY=sk-...
# or add to .env file
```

#### 2. Rate Limiting

```
Error: Rate limit exceeded
```

**Solution:** The pipeline batches embeddings (100 per request). If you still hit limits:

- Wait and retry (pipeline resumes from state)
- Use a higher-tier OpenAI account
- Reduce `CHUNK_MAX_TOKENS` to create fewer chunks

#### 3. Out of Memory

```
MemoryError: ...
```

**Solution:**

- Process smaller dataset first (`gjeldende-lover` instead of `gjeldende`)
- Increase system RAM
- Run on machine with more memory

#### 4. Corrupted State

```
Error: Invalid JSON in pipeline_state.json
```

**Solution:** Delete state file and reprocess:

```bash
rm data/pipeline_state.json
uv run python -m lovdata_pipeline process --force
```

#### 5. ChromaDB Lock Error

```
Error: database is locked
```

**Solution:** Ensure no other pipeline process is running:

```bash
# Check for running processes
ps aux | grep lovdata_pipeline

# Kill if needed
kill <PID>
```

### Debug Mode

Enable verbose logging:

```python
# In lovdata_pipeline/cli.py, change:
logging.basicConfig(level=logging.DEBUG, ...)
```

---

## Performance Tips

### 1. Use Persistent ChromaDB

Default mode. Fast and reliable.

### 2. Process Incrementally

Pipeline automatically detects changed files. Only reprocess when needed:

```bash
# First run: processes all files
uv run python -m lovdata_pipeline process

# Subsequent runs: only processes changed/new files
uv run python -m lovdata_pipeline process
```

### 3. Monitor OpenAI Usage

Embeddings are the main cost. Check usage:

- text-embedding-3-large: ~$0.13 per 1M tokens
- Estimate: ~10,000 chunks × 6,800 tokens avg = ~68M tokens = ~$9

### 4. Start Small

Test with `gjeldende-lover` (smaller dataset) before processing full `gjeldende`.

---

## Advanced Usage

### Custom Data Directory

```bash
uv run python -m lovdata_pipeline process --data-dir /custom/path
```

### Custom Chunking

```bash
uv run python -m lovdata_pipeline process --chunk-max-tokens 4000
```

### Custom Embedding Model

```bash
uv run python -m lovdata_pipeline process --embedding-model text-embedding-3-small
```

### Development Mode

```bash
# Install development dependencies
make install-dev

# Run tests
make test

# Run linters
make lint

# Format code
make format
```

---

## Data Management

### Backup

Important files to backup:

- `data/pipeline_state.json` - Processing state
- `data/chroma/` - Vector database

```bash
# Backup
tar -czf lovdata-backup.tar.gz data/pipeline_state.json data/chroma/

# Restore
tar -xzf lovdata-backup.tar.gz
```

### Reset Pipeline

Start fresh (deletes all processed data):

```bash
# Delete state and vectors
rm -rf data/pipeline_state.json data/chroma/

# Reprocess everything
uv run python -m lovdata_pipeline process
```

### Disk Space

Approximate sizes:

- `data/raw/` - ~10GB (compressed archives)
- `data/extracted/` - ~40GB (XML files)
- `data/chroma/` - ~5GB (vectors + metadata)
- Total: ~55GB for full `gjeldende` dataset

---

## Next Steps

- **[Quick Reference](QUICK_REFERENCE.md)** - Command cheat sheet
- **[Developer Guide](DEVELOPER_GUIDE.md)** - Extend the pipeline
- **[Functional Requirements](FUNCTIONAL_REQUIREMENTS.md)** - Specification
