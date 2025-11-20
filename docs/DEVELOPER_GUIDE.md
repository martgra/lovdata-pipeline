# Developer Guide

Guide for understanding, extending, and contributing to the Lovdata pipeline.

## Table of Contents

- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [How It Works](#how-it-works)
- [Data Models](#data-models)
- [Extending the Pipeline](#extending-the-pipeline)
- [Testing](#testing)
- [Development Workflow](#development-workflow)

---

## Architecture

### Design Philosophy

**Clarity Through Structure:**

- Service-oriented architecture with dependency injection
- Protocol-based interfaces for extensibility
- Clear separation of concerns across layers
- Single Responsibility Principle throughout

### Core Principle: Atomic Processing

Instead of stage-by-stage (chunk all → embed all → index all), each file completes fully:

```
for each changed file:
    parse XML → chunk → embed → index
```

**Benefits:**

- No intermediate files to manage
- Automatic cleanup on modification
- Simple error recovery (just skip failed file)
- Easy to understand and debug

### Architecture Layers

```
CLI (cli.py)
    ↓
Factory (pipeline.py - dependency injection)
    ↓
Orchestration (PipelineOrchestrator)
    ↓
Domain Services (XMLParsing, Chunking, Embedding, FileProcessing)
    ↓
Infrastructure (OpenAI, ChromaDB via Protocol interfaces)
    ↓
External Systems (lovlig, OpenAI API, ChromaDB)
```

### Key Design Patterns

1. **Dependency Injection** - Services receive dependencies via constructor
2. **Factory Pattern** - `create_pipeline_orchestrator()` wires up all dependencies
3. **Protocol Pattern** - `EmbeddingProvider` and `VectorStoreRepository` for extensibility
4. **Service Pattern** - Each service has a single, well-defined responsibility

---

## Project Structure

```
lovdata_pipeline/
├── __main__.py              # Entry point
├── cli.py                   # Typer-based CLI
├── pipeline.py              # Factory for dependency injection
├── state.py                 # Simple state tracking
├── lovlig.py                # Lovlig library wrapper
├── progress.py              # Progress tracking abstraction
│
├── config/
│   └── settings.py          # Environment-based configuration
│
├── domain/
│   ├── models.py            # Pydantic models
│   ├── embedding_provider.py    # Protocol interface
│   ├── vector_store.py          # Protocol interface
│   │
│   ├── services/            # Domain services
│   │   ├── chunking_service.py
│   │   ├── embedding_service.py
│   │   └── file_processing_service.py
│   │
│   ├── parsers/
│   │   └── lovdata_chunker.py   # Unified XML parsing and chunking
│   └── splitters/
│       └── token_counter.py     # Token counting
│
├── infrastructure/          # External service implementations
│   ├── chroma_vector_store.py   # VectorStoreRepository implementation
│   ├── jsonl_vector_store.py    # JSONL-based vector store
│   └── openai_embedding_provider.py  # EmbeddingProvider implementation
│
├── orchestration/
│   └── pipeline_orchestrator.py  # High-level workflow coordination
│
└── utils/
    └── file_ops.py          # File utilities

tests/
├── unit/                    # Fast, isolated tests
│   ├── state_test.py
│   ├── lovlig_test.py
│   ├── lovdata_chunker_test.py
│   ├── token_counter_test.py
│   ├── models_test.py
│   ├── settings_test.py
│   └── jsonl_vector_store_test.py
│
└── integration/             # End-to-end tests
    └── pipeline_test.py     # Service integration tests
```

### Key Components

| Component                                     | Purpose               | Responsibility                          |
| --------------------------------------------- | --------------------- | --------------------------------------- |
| `cli.py`                                      | CLI interface         | User commands and argument parsing      |
| `pipeline.py`                                 | Factory               | Dependency injection and service wiring |
| `orchestration/pipeline_orchestrator.py`      | Workflow coordination | Sync → identify → process → cleanup     |
| `domain/services/file_processing_service.py`  | File processing       | Parse → chunk → embed → index per file  |
| `domain/services/chunking_service.py`         | Chunking              | Parse XML and split into chunks         |
| `domain/services/embedding_service.py`        | Embedding             | Generate embeddings via provider        |
| `infrastructure/openai_embedding_provider.py` | OpenAI integration    | Concrete embedding provider             |
| `infrastructure/chroma_vector_store.py`       | ChromaDB integration  | Concrete vector store implementation    |
| `state.py`                                    | State tracking        | Tracks processed/failed documents       |
| `lovlig.py`                                   | Lovlig wrapper        | Syncs files, detects changes            |

---

## How It Works

### 1. Entry Point (`cli.py`)

Two commands:

- `process` - Run complete pipeline
- `status` - Show statistics

```python
@app.command()
def process(force: bool = False, ...):
    """Process all documents atomically."""
    config = {...}
    result = run_pipeline(config, progress_tracker)
```

### 2. Factory Pattern (`pipeline.py`)

```python
def create_pipeline_orchestrator(
    openai_api_key: str,
    embedding_model: str,
    chunk_max_tokens: int,
    chroma_path: str,
) -> PipelineOrchestrator:
    """Wire up all dependencies."""

    # Create infrastructure
    openai_client = OpenAI(api_key=openai_api_key)
    embedding_provider = OpenAIEmbeddingProvider(openai_client, embedding_model)

    chroma_client = chromadb.PersistentClient(path=chroma_path)
    vector_store = ChromaVectorStoreRepository(collection)

    # Create domain services
    chunking_service = ChunkingService(max_tokens=chunk_max_tokens)
    embedding_service = EmbeddingService(provider=embedding_provider)

    # Compose file processor
    file_processor = FileProcessingService(
        xml_parser=xml_parser,
        chunking_service=chunking_service,
        embedding_service=embedding_service,
        vector_store=vector_store,
    )

    # Create orchestrator
    return PipelineOrchestrator(
        file_processor=file_processor,
        vector_store=vector_store,
    )
```

### 3. Pipeline Orchestration (`PipelineOrchestrator`)

```python
def run(config: PipelineConfig, progress_tracker: ProgressTracker):
    """Main pipeline: sync → identify → process → cleanup."""

    # Initialize
    lovlig = Lovlig(config.data_dir, config.dataset_filter)
    state = ProcessingState(config.data_dir / "pipeline_state.json")

    # 1. Sync files from Lovdata
    lovlig.sync(force=config.force)

    # 2. Identify files to process
    changed_files = lovlig.get_changed_files()
    removed_files = lovlig.get_removed_files()
    to_process = [f for f in changed_files if not state.is_processed(f.doc_id, f.hash)]

    # 3. Process each file atomically
    for file_info in to_process:
        result = self._file_processor.process_file(file_info)
        if result.success:
            state.mark_processed(file_info.doc_id, file_info.hash, result.chunk_count)
        else:
            state.mark_failed(file_info.doc_id, file_info.hash, result.error_message)

    # 4. Clean up removed files
    for removal in removed_files:
        self._vector_store.delete_by_document_id(removal.document_id)
        state.remove(removal.document_id)
```

### 4. Per-File Processing (`FileProcessingService`)

```python
def process_file(file_info: FileInfo) -> FileProcessingResult:
    """Atomic: parse → chunk → embed → index."""

    # 1. Parse XML
    articles = self._xml_parser.parse_file(file_info.path)

    # 2. Chunk articles
    all_chunks = []
    for article in articles:
        chunks = self._chunking_service.chunk_article(
            article, file_info.doc_id, file_info.dataset
        )
        all_chunks.extend(chunks)

    # 3. Embed chunks
    enriched = self._embedding_service.embed_chunks(all_chunks)

    # 4. Index in vector store
    self._vector_store.upsert_chunks(enriched)

    return FileProcessingResult(
        success=True,
        chunk_count=len(all_chunks),
    )
```

### 5. State Tracking (`state.py`)

Simple JSON file:

```python
class ProcessingState:
    def mark_processed(self, doc_id: str, hash: str, vectors: list):
        """Record successful processing."""
        self.data["processed"][doc_id] = {
            "hash": hash,
            "vectors": vectors,
            "timestamp": datetime.now().isoformat()
        }

    def is_processed(self, doc_id: str, hash: str) -> bool:
        """Check if document already processed."""
        entry = self.data["processed"].get(doc_id)
        return entry and entry["hash"] == hash
```

### 5. Change Detection (`lovlig.py`)

Wrapper around lovlig library:

```python
class Lovlig:
    def sync(self):
        """Download/extract files from Lovdata."""
        lovlig.sync_datasets(self.dataset_filter)

    def get_changed_files(self) -> list[Path]:
        """Get added/modified files from state.json."""
        state = self._read_lovlig_state()
        return [f for f in state["files"]
                if f["status"] in ["added", "modified"]]
```

---

## Data Models

### ChunkMetadata

```python
class ChunkMetadata(BaseModel):
    """A single text chunk with metadata."""

    text: str                    # Chunk content
    dataset_name: str            # e.g. "gjeldende-lover"
    document_id: str             # e.g. "nl-18840614-003"
    section_heading: str         # Article heading
    absolute_address: str        # Lovdata URL
    chunk_index: int             # 0-based chunk number
    total_chunks: int            # Total for this article
    start_char: int              # Character offset in article
    end_char: int                # End character offset
    token_count: int             # Tokens in chunk
```

### EnrichedChunk

```python
class EnrichedChunk(BaseModel):
    """Chunk with embedding vector."""

    chunk: ChunkMetadata         # Original chunk
    embedding: list[float]       # Vector from OpenAI
    embedding_model: str         # Model name
    embedded_at: str             # ISO timestamp
```

### FileChange

```python
class FileChange(BaseModel):
    """Lovlig state entry."""

    relative_path: str           # Path within dataset
    document_id: str             # Extracted from filename
    hash: str                    # xxHash from lovlig
    status: str                  # "added" | "modified" | "removed"
```

---

## Extending the Pipeline

### Adding a New Chunking Strategy

Create new splitter in `domain/splitters/`:

```python
class CustomSplitter:
    def split_article(self, article: LegalArticle) -> list[ChunkMetadata]:
        # Your logic here
        return chunks
```

Use in `pipeline.py`:

```python
def chunk_article(xml_path, ...):
    # Custom chunker implementation
    chunker = CustomChunker()
    return chunker.chunk(xml_path)
```

### Adding a New Vector Database

1. Create wrapper in `infrastructure/`:

```python
class PineconeClient:
    def upsert(self, chunks: list[EnrichedChunk]) -> list[str]:
        # Upsert to Pinecone
        return vector_ids

    def delete(self, document_id: str) -> int:
        # Delete vectors by metadata filter
        return deleted_count
```

2. Update `pipeline.py`:

```python
def run_pipeline(config):
    # Replace ChromaVectorStoreRepository with custom implementation
    vector_store = PineconeVectorStore(...)
```

### Adding Pre/Post Processing

Add hooks in `pipeline.py`:

```python
def process_file(xml_path, ...):
    doc_id = xml_path.stem

    # Pre-processing hook
    if config.get("preprocess"):
        xml_path = preprocess_xml(xml_path)

    articles = extract_articles_from_xml(xml_path)
    chunks = [chunk_article(a, ...) for a in articles]

    # Post-processing hook
    if config.get("postprocess"):
        chunks = postprocess_chunks(chunks)

    enriched = embed_chunks(chunks, ...)
    ...
```

---

## Testing

### Test Organization

```
tests/
├── unit/              # Fast, isolated tests (~70 tests)
│   ├── state_test.py           # State tracking
│   ├── lovlig_test.py          # Lovlig wrapper
│   ├── xml_chunker_test.py     # XML parsing
│   └── ...
│
└── integration/       # End-to-end tests (~9 tests)
    ├── pipeline_test.py        # Full pipeline flow
    └── ...
```

### Running Tests

```bash
# All tests
uv run pytest tests/

# Unit tests only
uv run pytest tests/unit/

# Integration tests
uv run pytest tests/integration/

# With coverage
uv run pytest tests/ --cov=lovdata_pipeline --cov-report=html
```

### Writing Tests

**Unit test example:**

```python
def test_mark_processed():
    """Test marking document as processed."""
    state = ProcessingState(tmp_path / "state.json")

    state.mark_processed("doc1", "hash123", ["vec1", "vec2"])

    assert state.is_processed("doc1", "hash123")
    assert state.get_vectors("doc1") == ["vec1", "vec2"]
```

**Integration test example:**

```python
def test_process_file_success(tmp_path, mocker):
    """Test complete file processing."""
    # Mock OpenAI
    mock_embeddings = mocker.patch("openai.OpenAI.embeddings.create")
    mock_embeddings.return_value.data = [
        type("E", (), {"embedding": [0.1] * 3072})()
        for _ in range(10)
    ]

    # Process file
    result = process_file(xml_path, state, chroma, openai, config)

    # Verify
    assert result["status"] == "success"
    assert len(result["vectors"]) > 0
```

### Test Coverage

Current coverage: ~85%

Key areas covered:

- State tracking (100%)
- Lovlig wrapper (100%)
- XML parsing (95%)
- Chunking (90%)
- Pipeline integration (85%)

Uncovered:

- Some error paths
- CLI argument validation
- ChromaDB connection errors

---

## Development Workflow

### Setup

```bash
# Clone and install
git clone https://github.com/martgra/lovdata-pipeline.git
cd lovdata-pipeline
make install-dev

# Run tests
make test

# Run linters
make lint

# Format code
make format
```

### Pre-commit Hooks

Uses `prek` (not `pre-commit`):

```bash
# Install hooks
uv run prek install

# Run manually
uv run prek run --all-files
```

Checks:

- Ruff linting
- Pylint
- Type checking
- Test execution

### Making Changes

1. **Create branch**

   ```bash
   git checkout -b feature/my-feature
   ```

2. **Make changes**

   - Update code
   - Add/update tests
   - Update documentation

3. **Test**

   ```bash
   make test
   make lint
   ```

4. **Commit**

   ```bash
   git add .
   git commit -m "feat: add feature X"
   ```

5. **Push and PR**
   ```bash
   git push origin feature/my-feature
   # Open PR on GitHub
   ```

### Code Style

- **PEP 8** compliant
- **Type hints** on all functions
- **Docstrings** for public API (Google style)
- **Comments** explaining why, not what
- **100 character** line limit

**Good:**

```python
def chunk_article(
    article: dict, doc_id: str, dataset: str, max_tokens: int
) -> list[ChunkMetadata]:
    """Split article into token-sized chunks.

    Uses recursive splitting to respect XML structure while
    staying within token limits.

    Args:
        article: Dict with id, content, heading, address
        doc_id: Document identifier
        dataset: Dataset name
        max_tokens: Maximum tokens per chunk

    Returns:
        List of chunk metadata objects
    """
    # Convert to domain model for processing
    legal_article = LegalArticle(...)
```

---

## Debugging

### Enable Debug Logging

```python
# In cli.py
logging.basicConfig(level=logging.DEBUG, ...)
```

### Inspect State

```bash
# View state file
cat data/pipeline_state.json | jq '.'

# Check lovlig state
cat data/state.json | jq '.files[] | select(.status == "modified")'
```

### Test Single File

```python
# In pipeline.py, add:
if __name__ == "__main__":
    from pathlib import Path

    xml_path = Path("data/extracted/gjeldende-lover/nl/nl-18840614-003.xml")
    articles = extract_articles_from_xml(xml_path)
    print(f"Found {len(articles)} articles")
```

### Profile Performance

```bash
# Profile pipeline
uv run python -m cProfile -o profile.stats -m lovdata_pipeline process

# View results
uv run python -m pstats profile.stats
```

---

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for guidelines.

Key points:

- Follow code style
- Add tests for new features
- Update documentation
- Verify against [FUNCTIONAL_REQUIREMENTS.md](FUNCTIONAL_REQUIREMENTS.md)

---

## References

- **[User Guide](USER_GUIDE.md)** - How to use the pipeline
- **[Functional Requirements](FUNCTIONAL_REQUIREMENTS.md)** - Specification
- **[Quick Reference](QUICK_REFERENCE.md)** - Command cheat sheet
