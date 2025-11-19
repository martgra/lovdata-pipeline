# Quick Reference - Lovdata Pipeline

## Installation

```bash
make install
# or: uv sync
```

## Basic Usage

### Run Complete Pipeline

```bash
make full
# or: uv run python -m lovdata_pipeline full
```

### Run Individual Steps

```bash
# Download datasets from Lovdata
make sync
# or: uv run python -m lovdata_pipeline sync

# Parse XML and create chunks
make chunk
# or: uv run python -m lovdata_pipeline chunk

# Generate embeddings with OpenAI
make embed
# or: uv run python -m lovdata_pipeline embed

# Index vectors in ChromaDB
make index
# or: uv run python -m lovdata_pipeline index

# Clean up orphaned vectors
make reconcile
# or: uv run python -m lovdata_pipeline reconcile
```

## CLI Options

### Force Flags

```bash
# Force re-download all datasets
uv run python -m lovdata_pipeline sync --force-download

# Force reprocess all files (ignore processed state)
uv run python -m lovdata_pipeline chunk --force-reprocess

# Force re-embed all chunks
uv run python -m lovdata_pipeline embed --force-reembed

# Force full reprocessing
uv run python -m lovdata_pipeline full --force-download --force-reprocess
```

## Configuration

Create `.env` file:

```bash
# Dataset sync (required)
# Options: 'gjeldende' (both), 'gjeldende-lover' (laws only, smaller),
#          'gjeldende-sentrale-forskrifter' (regulations only)
LOVDATA_DATASET_FILTER=gjeldende
LOVDATA_RAW_DATA_DIR=./data/raw
LOVDATA_EXTRACTED_DATA_DIR=./data/extracted
LOVDATA_STATE_FILE=./data/state.json
LOVDATA_MAX_DOWNLOAD_CONCURRENCY=4

# Chunking (optional, defaults shown)
LOVDATA_CHUNK_MAX_TOKENS=6800
LOVDATA_CHUNK_OUTPUT_PATH=./data/chunks/legal_chunks.jsonl

# Embedding (required: API key)
LOVDATA_OPENAI_API_KEY=sk-...
LOVDATA_EMBEDDING_MODEL=text-embedding-3-large
LOVDATA_EMBEDDING_BATCH_SIZE=100
LOVDATA_ENRICHED_DATA_DIR=./data/enriched

# Vector Database (defaults shown)
LOVDATA_VECTOR_DB_TYPE=chroma                     # Only 'chroma' is supported
LOVDATA_VECTOR_DB_COLLECTION=legal_docs

# ChromaDB settings
LOVDATA_CHROMA_MODE=persistent                    # memory|persistent|client
LOVDATA_CHROMA_HOST=localhost                     # For client mode
LOVDATA_CHROMA_PORT=8000                          # For client mode
LOVDATA_CHROMA_PERSIST_DIRECTORY=./data/chroma    # For persistent mode

# Weaviate settings (when LOVDATA_VECTOR_DB_TYPE=weaviate)
# LOVDATA_WEAVIATE_URL=http://localhost:8080
# LOVDATA_WEAVIATE_API_KEY=your-key

# Qdrant settings (when LOVDATA_VECTOR_DB_TYPE=qdrant)
# LOVDATA_QDRANT_URL=http://localhost:6333
# LOVDATA_QDRANT_API_KEY=your-key

LOVDATA_MANIFEST_PATH=./data/manifest.json
```

## ChromaDB Modes

| Mode         | Storage       | Persistence        | Use Case                   |
| ------------ | ------------- | ------------------ | -------------------------- |
| `memory`     | RAM           | ❌ Lost on restart | Testing, development       |
| `persistent` | Local disk    | ✅ Saved           | Production, single machine |
| `client`     | Remote server | ✅ Saved           | Production, distributed    |

## Development Commands

```bash
# Run tests
make test
# or: uv run pytest

# Check code quality
make lint
# or: uv run ruff check lovdata_pipeline tests

# Format code
make format
# or: uv run ruff format lovdata_pipeline tests

# Check for secrets
make secrets
# or: uv run detect-secrets scan --baseline .secrets.baseline

# Clean cache files
make clean
```

## Project Structure

```
lovdata_pipeline/
├── cli.py               # Command-line interface
├── pipeline_steps.py    # Core pipeline functions
├── config/              # Configuration
├── domain/              # Business logic
└── infrastructure/      # External systems
```

## Data Flow

```
Step 1: Sync
  Lovdata API → data/raw/*.tar.bz2 → data/extracted/**/*.xml

Step 2: Chunk
  data/extracted/**/*.xml → data/chunks/legal_chunks.jsonl

Step 3: Embed
  data/chunks/*.jsonl → data/enriched/embedded_chunks.jsonl

Step 4: Index
  data/enriched/*.jsonl → ChromaDB
```

## State Files

| File                 | Purpose                                                    |
| -------------------- | ---------------------------------------------------------- |
| `data/state.json`    | Lovlig sync state (file hashes, changes from Lovdata)      |
| `data/manifest.json` | **Pipeline state** - tracks all stages (chunk/embed/index) |

## Common Tasks

### Process Only New Changes

```bash
# Default behavior - only processes changed files
make full
```

### Reprocess Everything

```bash
# Forces reprocessing of all files
uv run python -m lovdata_pipeline full --force-download --force-reprocess
```

### Check Pipeline Status

```bash
# View lovlig state for sync status
cat data/state.json | jq '.raw_datasets | to_entries[] | .value.files | length'

# View pipeline manifest (all stages)
cat data/manifest.json | jq '.documents | to_entries | length'

# Count chunks
wc -l data/chunks/legal_chunks.jsonl

# Count enriched chunks
wc -l data/enriched/embedded_chunks.jsonl
```

### Debug Failed Files

Check logs for error messages:

```bash
# Run with full logging
uv run python -m lovdata_pipeline chunk 2>&1 | tee chunk.log

# Search for errors
grep ERROR chunk.log
grep "Failed to process" chunk.log
```

### Query ChromaDB

```python
from lovdata_pipeline.infrastructure.chroma_client import ChromaClient

client = ChromaClient(collection_name="legal_docs")

# Get document count
count = client.count()
print(f"Documents in index: {count}")

# Query by metadata
results = client.query(
    query_embeddings=[[0.1, 0.2, ...]],
    n_results=5,
    where={"document_id": "nl-1234"}
)
```

## Scheduled Execution

### Using Cron

```bash
# Run daily at 2 AM
0 2 * * * cd /path/to/lovdata-pipeline && make full >> /var/log/lovdata-pipeline.log 2>&1
```

### Using Systemd Timer

Create `/etc/systemd/system/lovdata-pipeline.service`:

```ini
[Unit]
Description=Lovdata Pipeline

[Service]
Type=oneshot
WorkingDirectory=/path/to/lovdata-pipeline
ExecStart=/usr/local/bin/uv run python -m lovdata_pipeline full
User=lovdata
```

Create `/etc/systemd/system/lovdata-pipeline.timer`:

```ini
[Unit]
Description=Run Lovdata Pipeline Daily

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
```

Enable:

```bash
sudo systemctl enable lovdata-pipeline.timer
sudo systemctl start lovdata-pipeline.timer
```

## Docker Usage

### ChromaDB in Docker

Run ChromaDB vector database in Docker:

```bash
# Start ChromaDB
docker compose up -d

# Stop ChromaDB
docker compose down
```

### Pipeline in Docker (Optional)

Build and run the pipeline in a container:

```bash
# Build image
docker build -t lovdata-pipeline .

# Run with mounted data directory
docker run --rm \
  -v $(pwd)/data:/data \
  --env-file .env \
  lovdata-pipeline \
  uv run python -m lovdata_pipeline full

# Or run individual steps
docker run --rm -v $(pwd)/data:/data --env-file .env lovdata-pipeline uv run python -m lovdata_pipeline sync
```

## Troubleshooting

### Pipeline runs but doesn't process files

**Cause:** Files already marked as processed
**Solution:** Use force flags or delete state files

```bash
# Option 1: Force reprocess
uv run python -m lovdata_pipeline chunk --force-reprocess

# Option 2: Clear specific stage in manifest
python -c "import json; m=json.load(open('data/manifest.json')); [d.get('stages',{}).pop('chunking',None) for d in m['documents'].values()]; json.dump(m,open('data/manifest.json','w'),indent=2)"
make chunk
```

### Embedding fails with OpenAI errors

**Cause:** Rate limits or invalid API key
**Solution:** Check API key and reduce batch size

```bash
# Check API key
echo $LOVDATA_OPENAI_API_KEY

# Reduce batch size in .env
LOVDATA_EMBEDDING_BATCH_SIZE=50
```

### ChromaDB connection fails

**Cause:** ChromaDB server not running or wrong host/port
**Solution:** Start ChromaDB or update configuration

```bash
# Check if ChromaDB is running
curl http://localhost:8000/api/v1/heartbeat

# Start ChromaDB (if using server mode)
docker run -p 8000:8000 chromadb/chroma

# Or use persistent mode (no server)
LOVDATA_CHROMA_PERSIST_DIR=./data/chroma
```

### Out of memory during processing

**Cause:** Large XML files or accumulation
**Solution:** The pipeline is designed to be memory-safe; check for bugs

```bash
# Monitor memory usage
watch -n 1 'ps aux | grep python'

# Process fewer files at once (modify lovlig settings)
LOVDATA_MAX_DOWNLOAD_CONCURRENCY=1
```

## Performance Tips

### Speed up sync

- Increase concurrency: `LOVDATA_MAX_DOWNLOAD_CONCURRENCY=8`
- Use fast network connection

### Speed up chunking

- Already optimized (single-threaded XML parsing)
- Could parallelize across multiple processes (not implemented)

### Speed up embedding

- Increase batch size: `LOVDATA_EMBEDDING_BATCH_SIZE=200`
- Use faster model: `LOVDATA_EMBEDDING_MODEL=text-embedding-3-small`
- Upgrade OpenAI tier for higher rate limits

### Speed up indexing

- Use persistent ChromaDB (no network overhead)
- Batch upserts (already implemented)

## Additional Documentation

For detailed implementation notes, see the `docs/archive/` directory:

- Architecture details
- Chunking implementation
- Embedding implementation
- ChromaDB integration
- Pipeline manifest design
