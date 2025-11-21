# Development Guide

Guide for understanding, extending, and contributing to the Lovdata pipeline.

## Architecture

### Design Principle: Atomic Processing

Each file is fully processed before moving to the next:

```
for each changed file:
    parse XML → chunk → embed → index
```

**Benefits:**

- No intermediate state to manage
- Automatic cleanup on file changes
- Simple error recovery (retry failed files)
- Easy to understand and debug

### Architecture Layers

```
CLI (cli.py)
    ↓
Orchestrator (coordinates workflow)
    ↓
Services (chunking, embedding, processing)
    ↓
Infrastructure (OpenAI, vector stores)
    ↓
External Systems (lovlig, OpenAI API)
```

### Key Patterns

- **Service-Oriented**: Each service has single responsibility
- **Protocol Interfaces**: `EmbeddingProvider`, `VectorStoreRepository` for extensibility
- **Dependency Injection**: Services receive dependencies via constructor
- **Factory Pattern**: `create_pipeline_orchestrator()` wires dependencies

---

## Project Structure

```
lovdata_pipeline/
├── cli.py                   # CLI commands
├── pipeline.py              # Dependency injection factory
│
├── config/
│   └── settings.py          # Environment configuration
│
├── domain/
│   ├── models.py            # Pydantic data models
│   ├── services/            # Business logic
│   │   ├── chunking_service.py
│   │   ├── embedding_service.py
│   │   └── file_processing_service.py
│   └── parsers/
│       └── lovdata_chunker.py    # XML parsing & chunking
│
├── infrastructure/          # External integrations
│   ├── openai_embedding_provider.py
│   ├── chroma_vector_store.py
│   └── jsonl_vector_store.py
│
└── orchestration/
    └── pipeline_orchestrator.py   # Workflow coordination

tests/
├── unit/                    # Fast, isolated tests
└── integration/             # End-to-end tests
```

---

## Data Models

### ChunkMetadata

Core model representing a chunk of legal text:

```python
class ChunkMetadata(BaseModel):
    chunk_id: str              # Unique identifier
    document_id: str           # Source document
    dataset_name: str          # Dataset (e.g., "gjeldende-lover")
    content: str               # Text content
    token_count: int           # Token count
    section_heading: str       # Legal section heading
    absolute_address: str      # Lovdata URL
    source_hash: str           # File hash for change detection
    cross_refs: list[str]      # References to other laws
```

### EnrichedChunk

Chunk with embedding vector for storage:

```python
class EnrichedChunk(ChunkMetadata):
    embedding: list[float]     # Vector embedding
    embedding_model: str       # Model name
    embedded_at: str           # Timestamp

    @property
    def metadata(self) -> dict[str, Any]:
        """Get metadata dict with storage-compatible types.

        ChromaDB requires primitive types (str, int, float, bool, None).
        This property converts cross_refs list to comma-separated string.
        Use model_dump() for storage backends that support arrays (JSONL).
        """
```

### FileMetadata

Tracks file changes and processing state:

```python
class FileMetadata(BaseModel):
    relative_path: str         # Path from data dir
    document_id: str           # Document ID
    file_hash: str             # SHA256 hash
    dataset_name: str          # Dataset name
    status: FileStatus         # "added", "modified", "removed"
```

## How the Pipeline Works

### 1. Sync Data (`lovlig`)

```python
# lovlig library downloads files and tracks changes
lovlig.sync_dataset(
    dataset="gjeldende-lover",
    output_dir="data/extracted"
)

# Creates data/state.json with file hashes
{
  "files": {
    "nl-19940624-039.xml": {
      "hash": "abc123...",
      "status": "modified"
    }
  }
}
```

### 2. Identify Changes (`PipelineOrchestrator`)

```python
# Compare lovlig state with pipeline state
changed_files = identify_changed_files(
    lovlig_state="data/state.json",
    pipeline_state="data/pipeline_state.json"
)

# Returns list of files to process:
# - Added files (new)
# - Modified files (hash changed)
# - Removed files (deleted)
```

### 3. Process Files (`FileProcessingService`)

For each changed file:

```python
def process_file(file_info):
    # 1. Parse XML and chunk
    chunks = chunking_service.chunk_file(
        xml_path=file_info.path,
        doc_id=file_info.doc_id
    )

    # 2. Generate embeddings
    enriched = embedding_service.enrich_chunks(chunks)

    # 3. Store in vector DB
    vector_store.upsert_chunks(enriched)

    # 4. Update state
    update_pipeline_state(file_info, success=True)
```

### 4. Cleanup (`VectorStore`)

When files are removed or modified:

```python
# Remove old chunks for modified/removed files
vector_store.delete_chunks_by_document_id(doc_id)
```

## Extending the Pipeline

### Add Custom Embedding Provider

Implement the `EmbeddingProvider` protocol:

```python
from lovdata_pipeline.domain.embedding_provider import EmbeddingProvider

class CustomEmbeddingProvider(EmbeddingProvider):
    def embed_text(self, text: str) -> list[float]:
        """Generate embedding for text."""
        # Your implementation
        return embedding_vector

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for batch of texts."""
        # Your implementation
        return embedding_vectors
```

Wire it up in `pipeline.py`:

```python
def create_pipeline_orchestrator(...):
    embedding_provider = CustomEmbeddingProvider(...)
    embedding_service = EmbeddingService(provider=embedding_provider)
    ...
```

### Add Custom Vector Store

Implement the `VectorStoreRepository` protocol:

```python
from lovdata_pipeline.domain.vector_store import VectorStoreRepository

class CustomVectorStore(VectorStoreRepository):
    def upsert_chunks(self, chunks: list[EnrichedChunk]) -> None:
        """Store or update chunks.

        Note: Use chunk.metadata for stores with type restrictions (ChromaDB).
        Use chunk.model_dump() for stores supporting arrays (JSONL, Elasticsearch).
        """
        # Your implementation

    def delete_chunks_by_document_id(self, document_id: str) -> None:
        """Delete all chunks for a document."""
        # Your implementation

    def delete_chunks_by_dataset(self, dataset_name: str) -> None:
        """Delete all chunks for a dataset."""
        # Your implementation
```

**Metadata Type Considerations:** ChromaDB requires primitive types (str, int, float, bool, None) - use `chunk.metadata`. JSONL and Elasticsearch support arrays - use `chunk.model_dump()`.

### Add Custom Metadata Enricher

Extend chunk metadata during processing:

```python
# In lovdata_pipeline/domain/services/metadata_enrichment_service.py

def extract_custom_metadata(
    chunk_data: dict,
    xml_root: etree._Element,
    chunk_element: etree._Element | None = None
) -> dict:
    """Extract custom metadata from XML."""
    metadata = {}

    # Your extraction logic
    custom_field = xml_root.find('.//custom-element')
    if custom_field is not None:
        metadata["custom_field"] = custom_field.text

    return metadata

# Register the enricher
enrichment_service = MetadataEnrichmentService()
enrichment_service.register_enricher(extract_custom_metadata)
```

## Testing

### Run Tests

```bash
# All tests
make test

# Unit tests only
uv run pytest tests/unit/ -v

# Integration tests
uv run pytest tests/integration/ -v

# Specific test
uv run pytest tests/unit/test_chunking_service.py::test_chunk_file -v

# With coverage
make coverage
```

### Test Structure

**Unit Tests** (`tests/unit/`)

- Fast, isolated tests
- Mock external dependencies
- Test individual components
- Examples: `models_test.py`, `chunking_service_test.py`

**Integration Tests** (`tests/integration/`)

- Test service interactions
- Use real components where possible
- Verify end-to-end workflows
- Examples: `orchestrator_test.py`, `migration_test.py`

**End-to-End Tests** (`tests/end2end/`)

- Full pipeline workflows
- Test incremental processing behavior
- Verify state management

### Key Test Files

- **`models_test.py`** - Tests EnrichedChunk.metadata property and ChromaDB compatibility
- **`migration_test.py`** - Tests storage migration handles cross_refs conversion correctly
- **`orchestrator_test.py`** - Tests full pipeline orchestration
- **`state_consistency_test.py`** - Tests state management and error recovery

### Writing Tests

```python
import pytest
from lovdata_pipeline.domain.services.chunking_service import ChunkingService

def test_chunk_file():
    """Test chunking a legal document."""
    # Arrange
    service = ChunkingService(target_tokens=768)
    xml_path = "tests/fixtures/sample.xml"

    # Act
    chunks = service.chunk_file(
        xml_path=xml_path,
        doc_id="test-doc",
        dataset="test"
    )

    # Assert
    assert len(chunks) > 0
    assert all(chunk.token_count <= 8191 for chunk in chunks)
    assert all(chunk.document_id == "test-doc" for chunk in chunks)
```

### Test Fixtures

Create sample XML files in `tests/fixtures/`:

```xml
<!-- tests/fixtures/sample_law.xml -->
<?xml version="1.0" encoding="UTF-8"?>
<law>
  <article class="legalArticle">
    <section class="legalP" id="para-1-1">
      Test legal text content.
    </section>
  </article>
</law>
```

## Development Workflow

### Setup Development Environment

```bash
# Clone repository
git clone https://github.com/martgra/lovdata-pipeline.git
cd lovdata-pipeline

# Install dependencies
make install

# Install pre-commit hooks
uv run prek install
```

### Code Quality Tools

**Ruff** - Fast Python linter and formatter

```bash
# Format code
make format

# Lint code
make lint
```

**Pylint** - Additional code quality checks

```bash
# Run pylint
make pylint
```

**Type Checking**

```bash
# Run mypy (if configured)
uv run mypy lovdata_pipeline/
```

### Pre-commit Hooks

Automatically run on commit:

- Ruff formatting
- Ruff linting
- Pylint checks
- Trailing whitespace removal
- YAML validation

Managed by `prek` (not `pre-commit`):

```bash
# Install hooks
uv run prek install

# Run manually
uv run prek run --all-files
```

### Making Changes

1. **Create feature branch**

   ```bash
   git checkout -b feature/your-feature
   ```

2. **Make changes and test**

   ```bash
   # Edit code
   # Run tests
   make test

   # Check code quality
   make lint
   ```

3. **Commit changes**

   ```bash
   git add .
   git commit -m "Add feature: description"
   # Pre-commit hooks run automatically
   ```

4. **Push and create PR**
   ```bash
   git push origin feature/your-feature
   ```

## Requirements Checklist

Before merging changes, verify these functional requirements:

### Change Detection

- [ ] Pipeline only processes added/modified files
- [ ] Uses file hash comparison (lovlig vs pipeline state)
- [ ] Detects renamed files as removed + added
- [ ] Handles missing state files gracefully

### Change Handling

- [ ] Removed files: chunks deleted from vector store
- [ ] Modified files: old chunks deleted, new chunks added
- [ ] Added files: chunks created and stored
- [ ] Atomic per-file processing (all or nothing)

### Processing

- [ ] Each file processed independently
- [ ] Failures don't block other files
- [ ] Failed files tracked in state
- [ ] Progress reporting shows current file

### State Management

- [ ] `pipeline_state.json` tracks processed/failed files
- [ ] State updated after each file completes
- [ ] State includes file hash for change detection
- [ ] State recoverable if corrupted

### Index Consistency

- [ ] No orphaned chunks (file deleted but chunks remain)
- [ ] No duplicate chunks (same chunk stored twice)
- [ ] Chunks deleted when source file removed/modified
- [ ] Chunk IDs unique across all documents
- [ ] Metadata format compatible with storage backend (e.g., ChromaDB requires primitives)
- [ ] Migration between storage backends preserves all data correctly

### Error Handling

- [ ] Network errors: retry with exponential backoff
- [ ] Rate limits: respect API limits, queue requests
- [ ] File errors: log and continue with other files
- [ ] State corruption: detect and recover/rebuild

### Observability

- [ ] Progress: current file, completion percentage
- [ ] Statistics: processed, failed, removed counts
- [ ] Errors: clear error messages with context
- [ ] State: can inspect processing status

## Common Tasks

### Add New Command

Edit `cli.py`:

```python
@app.command()
def my_command(
    option: str = typer.Option("default", help="My option")
):
    """Command description."""
    # Implementation
    typer.echo(f"Running with {option}")
```

### Add New Service

1. Create service in `lovdata_pipeline/domain/services/`:

```python
# lovdata_pipeline/domain/services/my_service.py
class MyService:
    """Service description."""

    def __init__(self, dependency: SomeDependency):
        self._dependency = dependency

    def do_something(self, input_data: str) -> str:
        """Do something with input data."""
        # Implementation
        return result
```

2. Wire it up in `pipeline.py`:

```python
def create_pipeline_orchestrator(...):
    # Create service
    my_service = MyService(dependency=some_dependency)

    # Pass to orchestrator or other services
    orchestrator = PipelineOrchestrator(
        my_service=my_service,
        ...
    )
```

### Debug Processing

Enable detailed logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Inspect pipeline state:

```bash
# View processed files
cat data/pipeline_state.json | jq '.processed'

# View failed files with errors
cat data/pipeline_state.json | jq '.failed'
```

Test with small dataset:

```bash
# Process only 5 files
uv run lg process --storage jsonl --limit 5
```

## Contributing

### Guidelines

- **Keep it simple**: This is a straightforward ETL pipeline
- **Test your changes**: Add unit tests for new functionality
- **Follow conventions**: Use Ruff formatting, type hints
- **Update docs**: Document new features in GUIDE.md
- **Atomic commits**: One logical change per commit

### Pull Request Process

1. Fork the repository
2. Create feature branch
3. Make changes with tests
4. Run full test suite and linting
5. Update documentation if needed
6. Submit PR with clear description

### Code Style

- Use Ruff for formatting (automatic via pre-commit)
- Add type hints to all functions
- Write docstrings for public APIs
- Keep functions small and focused
- Prefer composition over inheritance

## Resources

- **Repository:** https://github.com/martgra/lovdata-pipeline
- **lovlig:** https://github.com/martgra/lovlig
- **OpenAI API:** https://platform.openai.com/docs
- **ChromaDB:** https://docs.trychroma.com
- **Pydantic:** https://docs.pydantic.dev
