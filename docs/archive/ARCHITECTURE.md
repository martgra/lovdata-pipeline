# Architecture

**Last Updated:** November 19, 2025

High-level architecture and design decisions for the Lovdata pipeline.

---

## Table of Contents

- [Overview](#overview)
- [Design Philosophy](#design-philosophy)
- [System Architecture](#system-architecture)
- [Data Flow](#data-flow)
- [Component Design](#component-design)
- [State Management](#state-management)
- [Error Handling](#error-handling)
- [Performance Considerations](#performance-considerations)
- [Security](#security)
- [Future Enhancements](#future-enhancements)

---

## Overview

The Lovdata pipeline is a simple, atomic document processing system that transforms Norwegian legal documents from XML into searchable vector embeddings.

### Core Principles

1. **Atomic Processing** - Each file completes fully or not at all
2. **Simplicity** - Direct implementation, no abstractions unless necessary
3. **Transparency** - Human-readable state, clear logging
4. **Reliability** - Recoverable from failures, idempotent operations

### Key Characteristics

- **Single command** - One entry point for all processing
- **Sequential execution** - Files processed one at a time
- **Stateful** - Tracks what's been processed to enable incremental updates
- **Self-contained** - No external orchestration required

---

## Design Philosophy

### Why Service-Oriented Architecture?

**Previous approach:** Direct function calls with passed dependencies

- Functions received many parameters
- Difficult to test in isolation
- Hard to swap implementations
- Complex dependency management

**Current approach:** Service-oriented with dependency injection

- Each service has a single responsibility
- Services receive dependencies via constructor
- Protocol interfaces enable alternative implementations
- Easy to mock for testing
- Clear dependency graph

### Why Protocol Interfaces?

**Benefits:**

- **Extensibility** - Swap OpenAI for local embeddings, ChromaDB for another vector DB
- **Testability** - Mock implementations for unit tests
- **Type Safety** - Python's Protocol for structural typing
- **No Abstract Classes** - Simpler than ABC inheritance

**Key Protocols:**

- `EmbeddingProvider` - Abstract embedding generation
- `VectorStoreRepository` - Abstract vector storage
- `ProgressTracker` - Abstract progress reporting

### Why Atomic Processing?

**Previous approach:** Stage-by-stage (chunk all → embed all → index all)

- Required complex state tracking across stages
- Difficult error recovery (which stage failed?)
- Intermediate files to manage
- Complex coordination between stages

**Current approach:** Atomic per-file

- Each file: parse → chunk → embed → index
- Simple state: processed or not processed
- Easy recovery: just skip processed files
- No intermediate files to manage

### Why Simple State?

**Previous approach:** Multiple state files + manifest

- `processed_files.json` - chunking state
- `embedded_files.json` - embedding state
- `manifest.json` - indexing state
- Complex reconciliation between files

**Current approach:** Single state file

- `pipeline_state.json` - everything in one place
- Hash-based version tracking
- Vector IDs for cleanup
- Atomic updates (temp file + rename)

---

## System Architecture

### High-Level Overview

```
┌─────────────────────────────────────────────────────────────┐
│                         User/CLI                             │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                    cli.py (Entry Point)                      │
│  • process command                                           │
│  • status command                                            │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ↓
┌─────────────────────────────────────────────────────────────┐
│              pipeline.py (Factory/DI Container)              │
│  • create_pipeline_orchestrator()                            │
│  • Wire up all dependencies                                  │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ↓
┌─────────────────────────────────────────────────────────────┐
│         orchestration/PipelineOrchestrator                   │
│  • Coordinate: sync → identify → process → cleanup           │
│  • Manage overall workflow                                   │
└──────┬──────────────────┬──────────────────┬───────────────┘
       │                  │                  │
       ↓                  ↓                  ↓
┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐
│   state.py  │  │  lovlig.py  │  │  domain/services/       │
│             │  │             │  │  FileProcessingService  │
│ • State     │  │ • Sync      │  │                         │
│   tracking  │  │ • Change    │  │  Coordinates:           │
│ • Hash      │  │   detection │  │  • XMLParsingService    │
│   checking  │  │             │  │  • ChunkingService      │
└─────────────┘  └─────────────┘  │  • EmbeddingService     │
                                   │                         │
                                   └────────┬────────────────┘
                                            │
                            ┌───────────────┴───────────────┐
                            ↓                               ↓
                ┌─────────────────────┐       ┌─────────────────────┐
                │  domain/            │       │  infrastructure/     │
                │  • xml_chunker      │       │  • OpenAIProvider   │
                │  • recursive_split  │       │  • ChromaVectorStore│
                │  • token_counter    │       │  (Protocol impls)   │
                └─────────────────────┘       └─────────────────────┘
                            │                               │
                            └───────────────┬───────────────┘
                                            ↓
┌─────────────────────────────────────────────────────────────┐
│                    External Services                         │
│  • Lovdata (via lovlig library)                              │
│  • OpenAI API (embeddings)                                   │
│  • ChromaDB (vector storage)                                 │
└─────────────────────────────────────────────────────────────┘
```

### Layer Responsibilities

**CLI Layer** (`cli.py`)

- Parse command-line arguments
- Validate configuration
- Create progress tracker
- Display results and errors

**Factory Layer** (`pipeline.py`)

- Dependency injection container
- Wire up all service dependencies
- Create and configure orchestrator
- Maintain backward compatibility

**Orchestration Layer** (`orchestration/pipeline_orchestrator.py`)

- Coordinate overall workflow
- Manage lovlig sync and state
- Process files through FileProcessingService
- Handle cleanup of removed files

**Domain Services** (`domain/services/`)

- **XMLParsingService** - Parse XML files into articles
- **ChunkingService** - Split articles into token-limited chunks
- **EmbeddingService** - Generate embeddings via provider
- **FileProcessingService** - Coordinate parse → chunk → embed → index

**Business Logic** (`domain/parsers/`, `domain/splitters/`)

- Pure functions and algorithms
- XML parsing logic
- Chunking algorithms (recursive, sentence-aware)
- Token counting
- Data models (Pydantic)

**Infrastructure Layer** (`infrastructure/`)

- **OpenAIEmbeddingProvider** - Implements `EmbeddingProvider` protocol
- **ChromaVectorStoreRepository** - Implements `VectorStoreRepository` protocol
- Concrete implementations of protocol interfaces

**State Management** (`state.py`, `lovlig.py`)

- Track processing history
- Detect file changes
- Manage vector IDs
- Coordinate with lovlig library

**External Services**

- Lovdata dataset sync
- OpenAI embeddings API
- ChromaDB vector storage

---

## Data Flow

### Complete Pipeline Flow

```
1. Sync
   │
   ├─→ lovlig.sync()
   │   └─→ Downloads/extracts files → data/extracted/
   │
   └─→ Creates data/state.json with file metadata

2. Detect Changes
   │
   ├─→ lovlig.get_changed_files()
   │   └─→ Returns files with status "added" or "modified"
   │
   └─→ lovlig.get_removed_files()
       └─→ Returns files with status "removed"

3. Process Each File (Atomic)
   │
   ├─→ Check if already processed (hash comparison)
   │   ├─→ Yes: Skip
   │   └─→ No: Continue with FileProcessingService
   │
   ├─→ XMLParsingService.parse_file()
   │   └─→ Returns list of ParsedArticle
   │
   ├─→ ChunkingService.chunk_article() for each article
   │   ├─→ Converts to LegalArticle
   │   ├─→ Uses XMLAwareRecursiveSplitter
   │   └─→ Returns list of ChunkMetadata
   │
   ├─→ EmbeddingService.embed_chunks()
   │   ├─→ Batches chunks (100 per batch)
   │   ├─→ Calls EmbeddingProvider.embed_batch()
   │   │   └─→ OpenAIEmbeddingProvider calls OpenAI API
   │   └─→ Returns list of EnrichedChunk
   │
   ├─→ VectorStoreRepository.upsert_chunks()
   │   └─→ ChromaVectorStoreRepository inserts into ChromaDB
   │
   └─→ Update State
       └─→ state.mark_processed(doc_id, hash, chunk_count)

4. Clean Up Removed Files
   │
   └─→ For each removed file:
       ├─→ VectorStoreRepository.delete_by_document_id()
       └─→ state.remove(document_id)
```

### Data Transformations

```
XML Document (source)
    ↓ XMLParsingService.parse_file()
List[ParsedArticle] (lightweight DTO)
    ↓ ChunkingService.chunk_article()
List[ChunkMetadata] (text, metadata, token count)
    ↓ EmbeddingService.embed_chunks()
List[EnrichedChunk] (text, metadata, embedding vector)
    ↓ VectorStoreRepository.upsert_chunks()
Vector IDs (stored in ChromaDB + state file)
```

### Service Dependencies

```
PipelineOrchestrator
    ├── FileProcessingService
    │   ├── XMLParsingService (no dependencies)
    │   ├── ChunkingService
    │   │   └── XMLAwareRecursiveSplitter
    │   │       └── TokenCounter
    │   ├── EmbeddingService
    │   │   └── EmbeddingProvider (protocol)
    │   │       └── OpenAIEmbeddingProvider (implementation)
    │   └── VectorStoreRepository (protocol)
    │       └── ChromaVectorStoreRepository (implementation)
    └── VectorStoreRepository (for cleanup)
```

---

## Component Design

### CLI Module (`cli.py`)

**Responsibility:** User interface

```python
@app.command()
def process(...):
    """Main command - process all documents."""
    # 1. Validate configuration
    # 2. Create progress tracker
    # 3. Call run_pipeline()
    # 4. Display results

@app.command()
def status(...):
    """Show statistics."""
    # 1. Load state
    # 2. Display counts
```

**Design decisions:**

- Uses Typer for CLI generation
- Rich for formatted output
- Minimal logic - delegates to pipeline
- Creates TUIProgressTracker for visual feedback

### Factory Module (`pipeline.py`)

**Responsibility:** Dependency injection and service wiring

```python
def create_pipeline_orchestrator(
    openai_api_key: str,
    embedding_model: str,
    chunk_max_tokens: int,
    chroma_path: str,
) -> PipelineOrchestrator:
    """Wire up all dependencies."""
    # Create infrastructure
    openai_client = OpenAI(...)
    embedding_provider = OpenAIEmbeddingProvider(openai_client, model)
    vector_store = ChromaVectorStoreRepository(collection)

    # Create domain services
    xml_parser = XMLParsingService()
    chunking = ChunkingService(max_tokens)
    embedding = EmbeddingService(embedding_provider)

    # Compose services
    file_processor = FileProcessingService(
        xml_parser, chunking, embedding, vector_store
    )

    # Create orchestrator
    return PipelineOrchestrator(file_processor, vector_store)

def run_pipeline(config: dict, progress_tracker) -> dict:
    """Backward compatibility wrapper."""
    orchestrator = create_pipeline_orchestrator(...)
    result = orchestrator.run(pipeline_config, progress_tracker)
    return {"processed": result.processed, "failed": result.failed}
```

**Design decisions:**

- Factory pattern for dependency injection
- All dependencies created in one place
- Clear dependency graph
- Maintains backward compatibility

### PipelineOrchestrator (`orchestration/pipeline_orchestrator.py`)

**Responsibility:** High-level workflow coordination

```python
class PipelineOrchestrator:
    def __init__(self, file_processor, vector_store):
        self._file_processor = file_processor
        self._vector_store = vector_store

    def run(self, config, progress_tracker) -> PipelineResult:
        # 1. Sync datasets
        # 2. Identify files to process
        # 3. Process each file
        # 4. Clean up removed files
```

**Design decisions:**

- Receives services via constructor (DI)
- Coordinates high-level stages
- Delegates actual work to services
- Returns structured result

### FileProcessingService (`domain/services/file_processing_service.py`)

**Responsibility:** Process one file atomically

```python
class FileProcessingService:
    def __init__(self, xml_parser, chunking, embedding, vector_store):
        self._xml_parser = xml_parser
        self._chunking_service = chunking
        self._embedding_service = embedding
        self._vector_store = vector_store

    def process_file(self, file_info: FileInfo) -> FileProcessingResult:
        # 1. Parse XML
        # 2. Chunk articles
        # 3. Embed chunks
        # 4. Index in vector store
        # Returns: success, chunk_count, error_message
```

**Design decisions:**

- Composes multiple services
- Atomic operation per file
- Error handling with cleanup
- Returns structured result

### Domain Services

**XMLParsingService** - Parse XML files

```python
class XMLParsingService:
    def parse_file(self, xml_path: Path) -> list[ParsedArticle]:
        # Extract articles from XML
        # Returns lightweight DTOs
```

**ChunkingService** - Split articles into chunks

```python
class ChunkingService:
    def __init__(self, max_tokens: int):
        self._splitter = XMLAwareRecursiveSplitter(max_tokens)

    def chunk_article(self, article, doc_id, dataset) -> list[ChunkMetadata]:
        # Convert to LegalArticle
        # Split using recursive splitter
        # Returns metadata objects
```

**EmbeddingService** - Generate embeddings

```python
class EmbeddingService:
    def __init__(self, provider: EmbeddingProvider, batch_size: int = 100):
        self._provider = provider
        self._batch_size = batch_size

    def embed_chunks(self, chunks, progress_callback=None) -> list[EnrichedChunk]:
        # Batch chunks
        # Call provider
        # Add embeddings to chunks
```

**Design decisions:**

- Each service has single responsibility
- Services are composable
- No direct I/O in domain logic
- Protocol interfaces for dependencies
  """Main orchestration."""
  # 1. Setup clients (Lovlig, OpenAI, ChromaDB)
  # 2. Sync files
  # 3. Get changes
  # 4. Process each file
  # 5. Clean up removed files
  # 6. Return statistics

def process_file(...) -> dict:
"""Atomic per-file processing.""" # 1. Parse XML # 2. Chunk articles # 3. Embed chunks # 4. Index vectors

### Infrastructure Layer

**OpenAIEmbeddingProvider** (`infrastructure/openai_embedding_provider.py`)

```python
class OpenAIEmbeddingProvider:
    """Concrete implementation of EmbeddingProvider protocol."""

    def __init__(self, client: OpenAI, model: str):
        self._client = client
        self._model = model

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        # Call OpenAI API
        # Extract embeddings
        # Return vectors

    def get_model_name(self) -> str:
        return self._model
```

**ChromaVectorStoreRepository** (`infrastructure/chroma_vector_store.py`)

```python
class ChromaVectorStoreRepository:
    """Concrete implementation of VectorStoreRepository protocol."""

    def __init__(self, collection):
        self._collection = collection

    def upsert_chunks(self, chunks: list[EnrichedChunk]):
        # Convert to ChromaDB format
        # Upsert vectors

    def delete_by_document_id(self, document_id: str):
        # Query by document_id
        # Delete vectors

    def get_collection_info(self) -> dict:
        # Return collection stats
```

**Design decisions:**

- Implement protocol interfaces
- Thin wrappers over external libraries
- Convert between domain models and external formats
- Handle API-specific concerns

### State Module (`state.py`)

**Responsibility:** Processing history tracking

```python
class ProcessingState:
    """Track processed and failed documents."""

    data: dict  # In-memory state
    path: Path  # File path

    def mark_processed(doc_id, hash, vectors)
    def mark_failed(doc_id, hash, error)
    def is_processed(doc_id, hash) -> bool
    def get_vectors(doc_id) -> list[str]
    def remove(doc_id)
    def stats() -> dict
```

**Design decisions:**

- Single JSON file (simple)
- Atomic writes (temp file + rename)
- Hash-based version tracking
- Vector IDs for cleanup

### Lovlig Module (`lovlig.py`)

**Responsibility:** Wrapper around lovlig library

```python
class Lovlig:
    """Minimal wrapper for lovlig library."""

    def sync() -> None
    def get_changed_files() -> list[FileChange]
    def get_removed_files() -> list[FileChange]
```

**Design decisions:**

- Thin wrapper (no business logic)
- Converts lovlig state to our models
- Single responsibility (change detection)

### Domain Modules

**Parsers** (`domain/parsers/`)

- `xml_chunker.py` - Parse legal XML documents
- Pure functions, no I/O
- lxml for XML parsing

**Splitters** (`domain/splitters/`)

- `recursive_splitter.py` - Split articles into chunks
- `token_counter.py` - Count tokens with tiktoken
- Respects token limits
- Preserves article structure

**Models** (`domain/models.py`)

- Pydantic models for type safety
- `ChunkMetadata` - Chunk without embedding
- `EnrichedChunk` - Chunk with embedding
- `FileMetadata`, `RemovalInfo` - Change detection results

### Protocol Interfaces

**EmbeddingProvider** (`domain/embedding_provider.py`)

```python
class EmbeddingProvider(Protocol):
    """Protocol for embedding generation."""

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a batch of texts."""

    def get_model_name(self) -> str:
        """Return the model name."""
```

**VectorStoreRepository** (`domain/vector_store.py`)

```python
class VectorStoreRepository(Protocol):
    """Protocol for vector storage."""

    def upsert_chunks(self, chunks: list[EnrichedChunk]):
        """Insert or update chunks in vector store."""

    def delete_by_document_id(self, document_id: str):
        """Delete all vectors for a document."""

    def get_collection_info(self) -> dict:
        """Return collection statistics."""
```

**Design decisions:**

- Use Protocol for structural typing
- No inheritance required
- Easy to add alternative implementations
- Type-safe at runtime with isinstance checks

---

## State Management

### State File Structure

**Location:** `data/pipeline_state.json`

```json
{
  "processed": {
    "doc-id-1": {
      "hash": "xxhash-value",
      "vectors": ["vec_id_1", "vec_id_2"],
      "timestamp": "2025-11-19T10:30:00Z"
    }
  },
  "failed": {
    "doc-id-2": {
      "hash": "xxhash-value",
      "error": "Invalid XML structure",
      "timestamp": "2025-11-19T10:35:00Z"
    }
  }
}
```

### State Operations

**Check if processed:**

```python
def is_processed(doc_id: str, hash: str) -> bool:
    entry = state.data["processed"].get(doc_id)
    return entry is not None and entry["hash"] == hash
```

**Mark as processed:**

```python
def mark_processed(doc_id: str, hash: str, vectors: list):
    state.data["processed"][doc_id] = {
        "hash": hash,
        "vectors": vectors,
        "timestamp": datetime.now(UTC).isoformat()
    }
    state._save()  # Atomic write
```

**Atomic write:**

```python
def _save(self):
    tmp_path = self.path.with_suffix(".tmp")
    with tmp_path.open("w") as f:
        json.dump(self.data, f, indent=2)
    tmp_path.rename(self.path)  # Atomic on POSIX
```

### Change Detection

**Lovlig state:** `data/state.json` (managed by lovlig library)

```json
{
  "files": [
    {
      "relative_path": "nl/nl-18840614-003.xml",
      "size": 12345,
      "hash": "abc123...",
      "last_changed": "2025-11-19T10:00:00Z",
      "status": "modified"
    }
  ]
}
```

**Change detection logic:**

```python
# File needs processing if:
# 1. Not in processed state, OR
# 2. Hash changed (content modified), OR
# 3. In failed state (retry)

if doc_id not in state.processed:
    return True  # New file

if state.processed[doc_id]["hash"] != current_hash:
    return True  # Modified file

if doc_id in state.failed:
    return True  # Retry failed file

return False  # Already processed
```

---

## Error Handling

### Per-File Isolation

Errors in one file don't stop the pipeline:

```python
def run_pipeline(config):
    stats = {"processed": 0, "failed": 0}

    for file_change in changed_files:
        try:
            result = process_file(file_change.path, ...)
            state.mark_processed(doc_id, hash, result["vectors"])
            stats["processed"] += 1

        except Exception as e:
            logger.error(f"Failed to process {doc_id}: {e}")
            state.mark_failed(doc_id, hash, str(e))
            stats["failed"] += 1
            continue  # Continue with next file

    return stats
```

### Error Recovery

**Automatic retry on next run:**

```python
# Failed files are retried automatically
if doc_id in state.failed:
    # Will be reprocessed on next run
    return True  # needs_processing
```

**Graceful shutdown:**

```python
# State saved after each file
# Ctrl+C during processing:
# - Completed files stay in state
# - Incomplete file not in state
# - Next run resumes from incomplete file
```

### Error Types

| Error Type                 | Handling            | Recovery          |
| -------------------------- | ------------------- | ----------------- |
| Network (OpenAI, ChromaDB) | Log, mark failed    | Retry next run    |
| Parse error (XML)          | Log, mark failed    | Manual fix needed |
| Out of memory              | Crash (no recovery) | Reduce dataset    |
| ChromaDB lock              | Retry with backoff  | Automatic         |
| Rate limit (OpenAI)        | Exponential backoff | Automatic         |

---

## Performance Considerations

### Bottlenecks

**1. OpenAI API calls** (largest bottleneck)

- Cost: ~$9 for 10,000 chunks
- Time: ~30 minutes for 10,000 chunks
- Mitigation: Batch requests (100 per call)

**2. ChromaDB writes**

- Time: ~100ms per upsert
- Mitigation: Could batch, but kept simple for now

**3. XML parsing**

- Time: ~10ms per file
- Not a bottleneck

**4. Network I/O (lovlig sync)**

- Time: ~5 minutes for full dataset
- Mitigation: Incremental updates

### Optimization Opportunities

**Batched ChromaDB writes:**

```python
# Current: 1 upsert per chunk
for chunk in enriched:
    chroma.upsert([chunk])

# Potential: Batch upserts
chroma.upsert(enriched)  # All at once
```

**Parallel file processing:**

```python
# Current: Sequential
for file in files:
    process_file(file)

# Potential: Parallel
with ThreadPoolExecutor() as executor:
    executor.map(process_file, files)
```

**Cost/benefit:** Not implemented because:

- Current approach is simple and reliable
- Performance is acceptable (~30 min for full dataset)
- Parallel processing adds complexity (state coordination)

### Scalability

**Current limits:**

- ~15,000 files in full dataset
- ~50,000 total chunks
- ~30 minutes for initial load
- ~5 minutes for incremental updates

**Scaling options:**

1. Batch ChromaDB writes (10x speedup)
2. Parallel processing (5-10x speedup)
3. Cache embeddings (avoid recomputing)
4. Incremental only (default behavior)

---

## Security

### API Keys

**OpenAI API key:**

- Stored in environment variable
- Never logged or printed
- Required for embeddings

**Best practices:**

```bash
# Use .env file (git-ignored)
OPENAI_API_KEY=sk-...

# Or export in shell
export OPENAI_API_KEY=sk-...
```

### Data Privacy

**Sensitive data:**

- Legal documents (public data from Lovdata)
- No personal information
- No authentication required

**ChromaDB:**

- Local storage by default
- No data sent to external services (except OpenAI for embeddings)

### Input Validation

**XML parsing:**

- Uses lxml (secure XML parser)
- No external entity expansion
- No XPath injection possible

**File paths:**

- All paths normalized
- No directory traversal
- Sandboxed to data directory

---

## Future Enhancements

### Potential Improvements

**1. Batch Operations**

- Batch ChromaDB upserts (10x speedup)
- Trade-off: More complex error recovery

**2. Parallel Processing**

- Process multiple files concurrently
- Trade-off: State coordination complexity

**3. Caching Layer**

- Cache embeddings (avoid recomputing on format changes)
- Trade-off: Storage cost, cache invalidation

**4. Incremental Embedding**

- Only re-embed changed chunks (not whole file)
- Trade-off: Complex chunking diffing logic

**5. Reconciliation**

- Periodic check: ChromaDB vs state file
- Catch orphaned vectors
- Already atomic, so not critical

**6. Monitoring**

- Metrics (processing time, error rate)
- Alerts (failures, performance degradation)
- Dashboard (real-time status)

**7. API/Service**

- REST API for querying vectors
- Background processing
- Multi-user support

### Non-Goals

**What we explicitly don't want:**

- ❌ Microservices architecture (overkill)
- ❌ Message queues (complexity)
- ❌ Distributed processing (not needed)
- ❌ Complex orchestration (Airflow, Prefect)
- ❌ Multiple databases (single ChromaDB is fine)
- ❌ GraphQL API (REST is sufficient)

**Rationale:** Keep it simple. Current architecture handles requirements well.

---

## Design Tradeoffs

### Simplicity vs Performance

**Choice:** Simplicity

- Sequential processing (easier to debug)
- Atomic per-file (no coordination needed)
- Direct library usage (fewer layers)

**Trade-off:** Could be faster with parallelization

- Current: ~30 minutes for full dataset
- Parallel: Could be ~5-10 minutes
- Decision: Not worth the complexity

### State Management

**Choice:** Single JSON file

- Easy to inspect (`cat pipeline_state.json`)
- Simple atomic updates
- No database required

**Trade-off:** Not suitable for >100k documents

- Current: 15k documents work fine
- Future: Could move to SQLite if needed

### Error Handling

**Choice:** Per-file isolation

- One failure doesn't stop pipeline
- Failed files retried on next run
- Simple to understand

**Trade-off:** Partial results possible

- Some files processed, some failed
- Need to check status after run
- Decision: Acceptable for batch processing

---

## References

- **[Developer Guide](DEVELOPER_GUIDE.md)** - Implementation details
- **[User Guide](USER_GUIDE.md)** - How to use the pipeline
- **[Functional Requirements](FUNCTIONAL_REQUIREMENTS.md)** - Requirements specification
- **[Incremental Updates](INCREMENTAL_UPDATES.md)** - Change detection details
