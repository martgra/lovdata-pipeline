# Lovdata Pipeline Architecture

> **Important:** This architecture implements the requirements defined in [FUNCTIONAL_REQUIREMENTS.md](FUNCTIONAL_REQUIREMENTS.md). All changes must be verified against those requirements.

## Overview

A Python CLI pipeline that processes Norwegian legal documents from Lovdata into a searchable vector database. Pure Python - no orchestration framework overhead.

## Design Principles

### 1. Layered Architecture

```
CLI (Entry Point)
    ↓
Pipeline Steps (Orchestration)
    ↓
Domain (Business Logic) + Infrastructure (I/O)
    ↓
External Systems (Lovdata, OpenAI, ChromaDB)
```

### 2. Separation of Concerns

- **CLI** - User interface, argument parsing
- **Pipeline Steps** - Coordinates workflow, handles errors
- **Domain** - Pure business logic (parsing, chunking, models)
- **Infrastructure** - External system wrappers (file I/O, APIs, databases)
- **Config** - Environment-based configuration

### 3. Incremental Processing

- Tracks file state to only process changes
- Detects added, modified, and removed files
- Maintains processing manifest for idempotency

## Project Structure

```
lovdata_pipeline/
├── __main__.py              # Entry point (python -m lovdata_pipeline)
├── cli.py                   # CLI commands and argument parsing
├── pipeline_steps.py        # Core pipeline orchestration functions
│
├── config/                  # Configuration management
│   └── settings.py          # Pydantic settings from environment
│
├── domain/                  # Pure business logic
│   ├── models.py            # Pydantic data models
│   ├── parsers/             # XML parsing logic
│   │   └── xml_chunker.py
│   └── splitters/           # Text chunking algorithms
│       ├── recursive_splitter.py
│       └── token_counter.py
│
└── infrastructure/          # External system wrappers
    ├── lovlig_client.py         # Lovdata sync (lovlig library)
    ├── chunk_writer.py          # Chunk JSONL output
    ├── chunk_reader.py          # Chunk JSONL input
    ├── enriched_writer.py       # Enriched chunk output
    ├── embedded_file_client.py  # Embedding state tracker
    ├── chroma_client.py         # Vector database client
    └── pipeline_manifest.py     # Processing state management
```

## Pipeline Steps

### 1. Sync (`sync_datasets`)

Downloads and extracts legal documents from Lovdata.

**What it does:**

- Uses lovlig library to download dataset archives
- Extracts XML files
- Updates state.json with file hashes and metadata
- Detects added, modified, and removed files

**Inputs:** None (reads from Lovdata API)
**Outputs:** Updated `data/state.json` and `data/extracted/**/*.xml`
**State:** Managed by lovlig library

### 2. Chunk (`chunk_documents`)

Parses XML documents and creates text chunks.

**What it does:**

- Reads unprocessed XML files from extracted data
- Parses legal structure (articles, paragraphs, sections)
- Splits text into chunks using XML-aware recursive splitter
- Respects token limits (6800 tokens default)
- Writes chunks to JSONL

**Inputs:** List of changed file paths
**Outputs:** `data/chunks/legal_chunks.jsonl`
**State:** Tracks processed files in `data/processed_files.json`

### 3. Embed (`embed_chunks`)

Generates embeddings for chunks using OpenAI.

**What it does:**

- Reads chunks from JSONL for modified files
- Batches chunks for efficient API usage
- Calls OpenAI embedding API
- Writes enriched chunks with embeddings
- Handles removals for deleted/modified files

**Inputs:** List of changed file paths
**Outputs:** `data/enriched/embedded_chunks.jsonl`
**State:** Tracks embedded files in `data/embedded_files.json`

### 4. Index (`index_embeddings`)

Stores embeddings in ChromaDB vector database.

**What it does:**

- Reads enriched chunks from JSONL
- Deletes vectors for removed/modified documents
- Upserts new/modified vectors with metadata
- Creates searchable vector index

**Inputs:** List of changed file paths, removed file metadata
**Outputs:** ChromaDB vector database
**State:** Managed by ChromaDB

### 5. Reconcile (`reconcile_index`)

Removes "ghost" documents from the index.

**What it does:**

- Compares lovlig state with ChromaDB index
- Identifies documents in index but not in lovlig state
- Removes orphaned vectors

**Inputs:** None (reads state and index)
**Outputs:** Updated ChromaDB vector database
**State:** None (stateless operation)

## Data Flow

```
Lovdata API
    ↓ (sync)
data/raw/*.tar.bz2
    ↓ (extract)
data/extracted/**/*.xml
    ↓ (chunk)
data/chunks/legal_chunks.jsonl
    ↓ (embed)
data/enriched/embedded_chunks.jsonl
    ↓ (index)
ChromaDB Vector Database
```

## State Management

The pipeline maintains several state files for incremental processing:

| File                        | Purpose              | Updated By    |
| --------------------------- | -------------------- | ------------- |
| `data/state.json`           | File hashes, changes | lovlig (sync) |
| `data/processed_files.json` | Chunking status      | chunk step    |
| `data/embedded_files.json`  | Embedding status     | embed step    |
| ChromaDB                    | Vector index         | index step    |

## Error Handling

### Retry Logic

Pipeline steps implement intelligent retry with exponential backoff:

- **Transient errors** (network, timeout) → Retry with backoff
- **Permanent errors** (file not found, parse error) → Log and skip
- **Max retries** → 3 attempts per file

### Partial Failures

- Individual file failures don't stop the pipeline
- Failed files are logged with context
- Statistics track success/failure counts
- Force flags allow reprocessing failed files

## Configuration

All configuration via environment variables:

```bash
# Dataset sync
LOVDATA_DATASET_FILTER=gjeldende
LOVDATA_RAW_DATA_DIR=./data/raw
LOVDATA_EXTRACTED_DATA_DIR=./data/extracted
LOVDATA_STATE_FILE=./data/state.json
LOVDATA_MAX_DOWNLOAD_CONCURRENCY=4

# Chunking
LOVDATA_CHUNK_MAX_TOKENS=6800
LOVDATA_CHUNK_OUTPUT_PATH=./data/chunks/legal_chunks.jsonl

# Embedding
LOVDATA_OPENAI_API_KEY=sk-...
LOVDATA_EMBEDDING_MODEL=text-embedding-3-large
LOVDATA_EMBEDDING_BATCH_SIZE=100
LOVDATA_ENRICHED_DATA_DIR=./data/enriched
LOVDATA_EMBEDDED_FILES_STATE=./data/embedded_files.json

# Indexing
LOVDATA_CHROMA_HOST=localhost
LOVDATA_CHROMA_PORT=8000
LOVDATA_CHROMA_COLLECTION=legal_docs
LOVDATA_MANIFEST_PATH=./data/manifest.json
```

## Performance Characteristics

### Memory Efficiency

- **Streaming architecture** - Processes one file at a time
- **Immediate writes** - No accumulation in memory
- **Chunked reading** - Reads JSONL line by line
- **Expected peak memory** - ~200MB for largest document

### Processing Speed

Approximate times for ~3,000 legal documents:

| Step  | Duration  | Bottleneck             |
| ----- | --------- | ---------------------- |
| Sync  | 5-10 min  | Network, extraction    |
| Chunk | 10-15 min | XML parsing            |
| Embed | 30-60 min | OpenAI API rate limits |
| Index | 5-10 min  | ChromaDB writes        |

### Scalability

- **Horizontal** - Can parallelize file processing (not implemented)
- **Vertical** - Low memory footprint, CPU-bound for parsing
- **Incremental** - Only processes changes, not full dataset

## Dependencies

### Core

- **chromadb** - Vector database
- **openai** - Embedding generation
- **lxml** - Fast XML parsing
- **pydantic** - Data validation and settings
- **tiktoken** - Token counting for chunking
- **tenacity** - Retry logic with backoff

### External Libraries

- **lovdata-processing** (lovlig) - Lovdata sync library
  - Git repo: https://github.com/martgra/lovlig

### Development

- **pytest** - Testing
- **ruff** - Linting and formatting
- **pylint** - Additional static analysis
- **prek** - Git hooks for quality checks

## Design Decisions

### Why Pure Python (No Dagster)?

**Previous approach:** Used Dagster for orchestration
**Current approach:** Pure Python CLI

**Rationale:**

- **Simplicity** - No server, no decorators, just functions
- **Speed** - Instant startup, no overhead
- **Debuggability** - Standard Python debugging works
- **Maintainability** - Less abstraction, clearer code flow

### Why Incremental Processing?

- **Efficiency** - Only process what changed (not 10GB every time)
- **Cost** - Reduces OpenAI API costs dramatically
- **Speed** - Updates complete in minutes, not hours

### Why JSONL for Intermediate Data?

- **Streamable** - Can read/write line by line
- **Human-readable** - Easy to inspect and debug
- **Appendable** - Can write as you go
- **Standard** - Well-supported by tools

### Why Pydantic Models?

- **Validation** - Runtime type checking and constraints
- **Serialization** - Built-in JSON conversion
- **Documentation** - Field descriptions and examples
- **IDE support** - Better autocomplete and type hints

## Testing Strategy

See [TEST_COVERAGE.md](TEST_COVERAGE.md) for detailed test documentation.

- **Unit tests** - Domain logic and models
- **Integration tests** - Infrastructure components
- **End-to-end tests** - Full pipeline flows

## Deployment

See [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md) for containerized deployment.

The pipeline can run as:

- **CLI tool** - Manual invocation
- **Cron job** - Scheduled execution
- **Docker container** - Isolated environment
- **GitHub Actions** - CI/CD automation
