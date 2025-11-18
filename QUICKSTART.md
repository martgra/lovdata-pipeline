# Quick Start Guide - Lovdata Pipeline

## 🚀 Get Started in 5 Minutes

### 1. Install Dependencies

```bash
# Using UV (recommended)
make install

# Or using pip
pip install -e .
```

### 2. Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your API keys
nano .env  # or use your preferred editor
```

**Minimum required configuration:**

```bash
OPENAI_API_KEY=sk-your-api-key-here
```

**Optional configuration:**

```bash
# Embedding Performance Tuning
EMBEDDING_BATCH_SIZE=2048        # Texts per API request (max: 2048, default: 2048)
EMBEDDING_RATE_LIMIT_DELAY=0.5   # Seconds between batches (default: 0.5)

# File Processing Limits
MAX_FILES=100                     # Limit number of files to process (0 = all, default: 0)

# Langfuse Observability (optional)
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com
```

### 3. Start Dagster UI

```bash
make dagster

# Or directly:
dagster dev -m lovdata_pipeline
```

Open http://localhost:3000 in your browser.

### 4. Run the Pipeline

**Option A: Via Dagster UI**

1. Navigate to "Assets" tab
2. Click "Materialize all"
3. Watch the pipeline execute!

**Option B: Via CLI**

```bash
# Full pipeline (all ~4,200 documents)
make dagster-job

# Or directly:
dagster job execute -m lovdata_pipeline -j lovdata_processing_job

# Test with a small subset (recommended for first run)
MAX_FILES=10 dagster asset materialize -m lovdata_pipeline --select "lovdata_sync,changed_legal_documents,parsed_legal_chunks"
```

**Testing with Limited Files:**

To avoid long processing times or memory issues, use environment variables:

```bash
# Process only 10 files (great for testing)
MAX_FILES=10 make dagster-job

# Process 100 files
MAX_FILES=100 make dagster-job

# Process 1000 files (default safety limit if MAX_FILES not set)
MAX_FILES=1000 make dagster-job

# WARNING: Processing all files without MAX_FILES set will auto-limit to 1000
# to prevent memory issues. To process more, set MAX_FILES explicitly:
MAX_FILES=5000 make dagster-job

# Adjust embedding settings for very long documents
export EMBEDDING_MAX_TOKENS=7000  # Reduce token limit per batch (default: 8000)
export EMBEDDING_BATCH_SIZE=1000   # Reduce batch size (default: 2048)
export EMBEDDING_RATE_LIMIT_DELAY=1.0  # Increase delay between batches (default: 0.5s)

# Run with custom settings
MAX_FILES=100 make dagster-job
```

**Note:** The pipeline has a safety limit of 1000 files per run when MAX_FILES is not set to prevent memory issues with Dagster's multiprocess executor. To process more files, set MAX_FILES explicitly.

**Resuming Failed Runs:**

The pipeline automatically saves checkpoints during embedding generation. If a run fails partway through:

```bash
# Simply re-run the pipeline - it will resume from the last successful batch
make dagster-job

# Or re-materialize just the failed asset
dagster asset materialize -m lovdata_pipeline --select document_embeddings

# Checkpoints are stored in data/checkpoints/ and auto-deleted on success
# To disable checkpointing (start fresh every time):
export ENABLE_EMBEDDING_CHECKPOINT=false
```

This prevents wasting API costs by re-embedding already processed chunks!

## 📊 What Happens

The pipeline will:

1. **Sync** - Download and extract Lovdata documents using lovlig
2. **Parse** - Extract legal chunks from XML with intelligent splitting:
   - Chunks at legalArticle (§) level by default
   - **XML-aware splitting**: Large articles split at legalP (paragraph) boundaries
   - **Token-aware**: Respects 6800 token limit (safe for 8K embedding models)
   - **Preserves metadata**: All XML hierarchy info maintained across splits
3. **Embed** - Generate embeddings using OpenAI with checkpoint/resume
4. **Load** - Store in ChromaDB for semantic search

### Intelligent XML Chunking

The parser uses a hierarchical splitting strategy:

```
Step 1: Parse at legalArticle (§) level
        ↓
Step 2: Check token count
        ↓
   < 6800 tokens?
   YES → Keep as single chunk
   NO  → Try XML-aware split
        ↓
Step 3: Split at legalP boundaries
        (preserves paragraph structure)
        ↓
   Still too large?
   YES → Fall back to text splitting
   NO  → Use XML-split chunks
```

This ensures legal document structure is preserved while staying within embedding model limits!

## 🔍 Monitor Progress

- **Dagster UI**: http://localhost:3000 - Real-time logs and metrics
- **Langfuse** (optional): Track costs and performance at https://cloud.langfuse.com

## 📁 Data Locations

After running, you'll find:

```
data/
├── raw/           # Downloaded ZIP files from Lovdata
├── extracted/     # Extracted XML documents
├── chromadb/      # Vector database storage
└── state.json     # lovlig change tracking
```

## 🧪 Run Tests

```bash
make test

# With coverage
pytest --cov=lovdata_pipeline
```

## 🐳 Using Docker

```bash
# Build and start
make docker-build
make docker-up

# View logs
make docker-logs

# Stop
make docker-down
```

## 🆘 Troubleshooting

**Import errors?**

```bash
# Install system dependencies (Ubuntu/Debian)
sudo apt-get install libxml2-dev libxslt-dev

# Reinstall lxml
pip install --force-reinstall lxml
```

**Token limit errors in embeddings?**

The pipeline uses token-aware batching to prevent exceeding OpenAI's 8,192 token limit per request. If you still encounter token errors:

```bash
# Reduce the token limit per batch (default: 8000)
export EMBEDDING_MAX_TOKENS=6000

# This creates more, smaller batches for very long documents
```

**Memory issues during parsing?**

```bash
# Limit files processed per run (useful for testing)
export MAX_FILES=100

# Process remaining files in subsequent runs
```

**lovlig not found?**

```bash
# Install from GitHub
pip install git+https://github.com/martgra/lovlig.git
```

**No data syncing?**

- Check your internet connection
- Verify Lovdata API is accessible
- Check lovlig logs in Dagster UI

## 📚 Next Steps

1. **Configure Langfuse** for cost tracking (optional)
2. **Enable daily schedule** in Dagster UI
3. **Customize chunking** in `lovdata_pipeline/parsers/lovdata_xml_parser.py`
4. **Query ChromaDB** for semantic search (see README_PIPELINE.md)

## 🎯 Production Deployment

See [README_PIPELINE.md](README_PIPELINE.md) for:

- Production configuration
- PostgreSQL setup
- Monitoring and alerting
- Performance tuning

---

Need help? Check the full documentation in [README_PIPELINE.md](README_PIPELINE.md)
