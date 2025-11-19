# Developer Guide

Guide for understanding, extending, and contributing to the Lovdata pipeline.

## Table of Contents

- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Pipeline Implementation](#pipeline-implementation)
- [Data Models](#data-models)
- [State Management](#state-management)
- [Extending the Pipeline](#extending-the-pipeline)
- [Testing](#testing)
- [Development Workflow](#development-workflow)

---

## Architecture

### Design Principles

**1. Layered Architecture**

```
CLI (Entry Point)
    ↓
Pipeline Steps (Orchestration)
    ↓
Domain (Business Logic) + Infrastructure (I/O)
    ↓
External Systems (Lovdata, OpenAI, ChromaDB)
```

**2. Separation of Concerns**

- **CLI** (`cli.py`) - User interface, argument parsing
- **Pipeline Steps** (`pipeline_steps.py`) - Orchestration, error handling
- **Domain** (`domain/`) - Pure business logic (parsing, chunking, models)
- **Infrastructure** (`infrastructure/`) - External systems (file I/O, APIs, databases)
- **Config** (`config/`) - Environment-based configuration

**3. Incremental Processing**

- Tracks file state to only process changes
- Detects added, modified, and removed files
- Maintains processing manifest for idempotency

See [FUNCTIONAL_REQUIREMENTS.md](FUNCTIONAL_REQUIREMENTS.md) for the specification.

### Data Flow

```
Lovdata API
    ↓ sync
data/raw/*.tar.bz2
    ↓ extract
data/extracted/**/*.xml
    ↓ chunk
data/chunks/legal_chunks.jsonl
    ↓ embed
data/enriched/embedded_chunks.jsonl
    ↓ index
ChromaDB Vector Database
```

---

## Project Structure

```
lovdata_pipeline/
├── __main__.py              # Entry point (python -m lovdata_pipeline)
├── cli.py                   # CLI commands using typer
├── pipeline_steps.py        # Core pipeline orchestration functions
├── pipeline_context.py      # Dependency injection container
│
├── config/                  # Configuration management
│   └── settings.py          # Pydantic settings from environment
│
├── domain/                  # Pure business logic
│   ├── models.py            # Pydantic data models
│   ├── parsers/             # XML parsing logic
│   │   └── xml_chunker.py   # lxml-based legal XML parser
│   └── splitters/           # Text chunking algorithms
│       ├── recursive_splitter.py  # XML-aware recursive splitter
│       └── token_counter.py       # tiktoken wrapper
│
└── infrastructure/          # External system wrappers
    ├── lovlig_client.py         # Lovdata sync (lovlig library)
    ├── chunk_writer.py          # Chunk JSONL output
    ├── chunk_reader.py          # Chunk JSONL input
    ├── enriched_writer.py       # Enriched chunk output
    ├── embedded_file_client.py  # Embedding state tracker (legacy)
    ├── chroma_client.py         # Vector database client
    └── pipeline_manifest.py     # Unified processing state management
```

### Key Design Decisions

**Why Typer for CLI?**

- **Modern** - Type hints drive CLI generation
- **Beautiful** - Rich formatting and help text
- **Automatic** - Less boilerplate than argparse
- **Standard** - Built on click, battle-tested

**Why Dependency Injection?**

- **Testability** - Easy to inject mocks and test doubles
- **Reusability** - Clients created once, reused across functions
- **Clarity** - Explicit dependencies, no hidden state
- **Performance** - Avoid repeated client instantiation

**Why Pure Python (No Orchestration)?**

- **Simplicity** - No server, no decorators, just functions
- **Speed** - Instant startup, no overhead
- **Debuggability** - Standard Python debugging works
- **Maintainability** - Less abstraction, clearer code flow

**Why JSONL for Intermediate Data?**

- **Streamable** - Can read/write line by line
- **Human-readable** - Easy to inspect and debug
- **Appendable** - Can write as you go
- **Standard** - Well-supported by tools

**Why Pydantic Models?**

- **Validation** - Runtime type checking and constraints
- **Serialization** - Built-in JSON conversion
- **Documentation** - Field descriptions and examples
- **IDE support** - Better autocomplete and type hints

---

## Pipeline Implementation

### Dependency Injection with PipelineContext

All pipeline dependencies are managed through `PipelineContext`:

```python
from lovdata_pipeline.pipeline_context import PipelineContext

# Create context with all dependencies
ctx = PipelineContext.from_settings()

# Access any client through context
ctx.lovlig_client.sync_datasets()
ctx.chunk_writer.write_chunks(chunks)
ctx.openai_client.embeddings.create(...)
ctx.chroma_client.upsert(...)
```

**Benefits:**

- Settings loaded once
- Clients created once
- Easy to mock for testing
- Clear dependency graph

### Pipeline Steps

Each pipeline step is implemented as a pure Python function in `pipeline_steps.py`:

```python
def sync_datasets(
    force_download: bool = False
) -> dict:
    """Download and extract legal documents from Lovdata."""
    ctx = _create_context()
    stats = ctx.lovlig_client.sync_datasets(force_download)
    return stats

def chunk_documents(
    changed_file_paths: list[str],
    removed_metadata: list[dict],
) -> dict:
    """Parse XML documents and create text chunks."""
    ctx = _create_context()
    # Process files using context dependencies
    ...
```

def index_embeddings(
changed_file_paths: list[str],
removed_metadata: list[dict]
) -> None:
"""Store embeddings in ChromaDB vector database."""
...

def reconcile_index() -> None:
"""Remove orphaned vectors from ChromaDB."""
...

````

### Error Handling Pattern

Pipeline steps implement intelligent retry with exponential backoff:

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type(TransientError)
)
def process_file(file_path: str) -> list[Chunk]:
    """Process a single file with retry logic."""
    try:
        # Process file
        return chunks
    except XMLParseError as e:
        # Permanent error - don't retry
        logger.error(f"Failed to parse {file_path}: {e}")
        raise PermanentError(e) from e
    except ConnectionError as e:
        # Transient error - retry
        logger.warning(f"Connection failed, retrying: {e}")
        raise TransientError(e) from e
````

**Error Classification:**

- **Transient errors** (network, timeout) → Retry with backoff
- **Permanent errors** (parse failure, missing file) → Log and skip
- **Max retries** → 3 attempts per file

### Memory Management

Pipeline uses streaming architecture to handle large datasets:

```python
def chunk_documents(changed_file_paths: list[str], ...) -> None:
    """Process files one at a time."""
    writer = ChunkWriter(settings.chunk_output_path)

    with writer:
        for file_path in changed_file_paths:
            # Process ONE file at a time
            chunker = LovdataXMLChunker(file_path)
            articles = chunker.extract_articles()  # Parse one file

            for article in articles:
                chunks = splitter.split_article(article)
                writer.write_chunks(chunks)  # Immediate write

            # File goes out of scope, memory freed
```

**Benefits:**

- Peak memory: ~200 MB (size of largest file)
- No accumulation in memory
- Can process unlimited files

---

## Data Models

All data models use Pydantic for validation and serialization.

### Core Models

```python
from pydantic import BaseModel, Field

class LegalChunk(BaseModel):
    """A chunk of legal text."""
    chunk_id: str = Field(..., description="Unique chunk identifier")
    document_id: str = Field(..., description="Source document ID")
    content: str = Field(..., description="Text content")
    token_count: int = Field(..., ge=0, description="Number of tokens")
    section_heading: str = Field(default="", description="Section title")
    absolute_address: str = Field(..., description="Hierarchical address")
    split_reason: SplitReason = Field(..., description="Why chunk was split")
    parent_chunk_id: str | None = Field(None, description="Parent chunk ID if split")

class EnrichedChunk(LegalChunk):
    """Chunk with embedding."""
    embedding: list[float] = Field(..., description="Vector embedding")
    embedding_model: str = Field(..., description="Model used")

class FileMetadata(BaseModel):
    """File processing metadata."""
    dataset_name: str
    relative_path: str
    file_hash: str
    file_size_bytes: int
    last_changed: datetime
    document_id: str
```

See `lovdata_pipeline/domain/models.py` for all models.

---

## State Management

The pipeline maintains state across two primary files:

### State Files

| File                 | Purpose                                     | Updated By         | Format |
| -------------------- | ------------------------------------------- | ------------------ | ------ |
| `data/state.json`    | File hashes, changes (from Lovdata)         | lovlig (sync)      | JSON   |
| `data/manifest.json` | **All pipeline stages** (chunk/embed/index) | All pipeline steps | JSON   |

The manifest is the **single source of truth** for pipeline state, tracking:

- Document metadata (hash, size, dataset)
- Stage completion (chunking, embedding, indexing)
- Version history and retry counts
- Error states and classifications

### Incremental Processing Logic

```python
# In sync step
lovlig_client = LovligClient(settings, manifest=manifest)
changed_paths, removed_metadata = lovlig_client.sync_datasets()
# Updates data/state.json with file hashes

# In chunk step
unprocessed = lovlig_client.get_unprocessed_files()
# Compares state.json hashes with manifest.is_stage_completed("chunking")
# Returns files where: file.hash != manifest.current_version.file_hash

for file_path in unprocessed:
    # Process file
    chunks = process(file_path)
    writer.write_chunks(chunks)

    # Mark as processed - updates manifest
    lovlig_client.mark_file_processed(dataset, path)
    # Calls manifest.complete_stage(document_id, "chunking")

# Similar pattern for embedding and indexing stages
```

See [INCREMENTAL_UPDATES.md](INCREMENTAL_UPDATES.md) for detailed logic.

---

## Extending the Pipeline

### Switching Vector Databases

The pipeline uses an abstract `VectorDBClient` interface, allowing you to swap ChromaDB for alternatives like Pinecone, Weaviate, or Qdrant.

**Abstract Interface** (`infrastructure/vector_db_client.py`):

```python
from abc import ABC, abstractmethod

class VectorDBClient(ABC):
    """Abstract base class for vector database clients."""

    @abstractmethod
    def upsert(self, ids: list[str], embeddings: list[list[float]],
               metadatas: list[dict] | None = None) -> None:
        """Insert or update vectors."""
        pass

    @abstractmethod
    def delete(self, ids: list[str]) -> None:
        """Delete vectors by ID."""
        pass

    @abstractmethod
    def get_vector_ids(self, where: dict | None = None) -> list[str]:
        """Get all vector IDs matching filter."""
        pass

    @abstractmethod
    def query(self, query_embeddings: list[list[float]], n_results: int = 10,
              where: dict | None = None) -> dict:
        """Query similar vectors."""
        pass

    @abstractmethod
    def get_collection_info(self) -> dict:
        """Get collection metadata."""
        pass

    @abstractmethod
    def delete_collection(self) -> None:
        """Delete entire collection."""
        pass
```

**Example: Adding Pinecone Support**

1. **Create new client** in `infrastructure/pinecone_client.py`:

```python
from pinecone import Pinecone
from lovdata_pipeline.infrastructure.vector_db_client import VectorDBClient

class PineconeClient(VectorDBClient):
    """Pinecone implementation of VectorDBClient."""

    def __init__(self, api_key: str, index_name: str, environment: str):
        self.client = Pinecone(api_key=api_key, environment=environment)
        self.index = self.client.Index(index_name)

    def upsert(self, ids: list[str], embeddings: list[list[float]],
               metadatas: list[dict] | None = None) -> None:
        """Insert or update vectors in Pinecone."""
        vectors = [
            (id, embedding, metadata)
            for id, embedding, metadata in zip(ids, embeddings, metadatas or [{}] * len(ids))
        ]
        self.index.upsert(vectors=vectors)

    def delete(self, ids: list[str]) -> None:
        """Delete vectors from Pinecone."""
        self.index.delete(ids=ids)

    # ... implement other abstract methods ...
```

2. **Add settings** to `config/settings.py`:

```python
class LovdataSettings(BaseSettings):
    # ... existing settings ...

    # Vector database selection
    vector_db_type: str = Field(default="chroma", description="Vector DB: chroma or pinecone")

    # Pinecone settings
    pinecone_api_key: str | None = Field(None, description="Pinecone API key")
    pinecone_index_name: str = Field(default="lovdata", description="Pinecone index name")
    pinecone_environment: str = Field(default="gcp-starter", description="Pinecone environment")
```

3. **Update PipelineContext** to choose client:

```python
@classmethod
def from_settings(cls, settings: LovdataSettings | None = None) -> "PipelineContext":
    """Create pipeline context from settings."""
    if settings is None:
        settings = get_settings()

    # ... other clients ...

    # Choose vector DB client based on settings
    if settings.vector_db_type == "pinecone":
        vector_client = PineconeClient(
            api_key=settings.pinecone_api_key,
            index_name=settings.pinecone_index_name,
            environment=settings.pinecone_environment,
        )
    else:  # default to ChromaDB
        vector_client = ChromaClient(
            mode=settings.chroma_mode,
            host=settings.chroma_host,
            port=settings.chroma_port,
            collection_name=settings.chroma_collection,
            persist_directory=settings.chroma_persist_directory,
        )

    return cls(
        # ... other dependencies ...
        chroma_client=vector_client,  # Now a VectorDBClient
    )
```

**Why This Abstraction?**

- **Flexibility** - Switch databases without changing pipeline code
- **Testing** - Easy to create mock implementations
- **Future-proof** - New vector DBs can be added cleanly
- **SOLID** - Follows Dependency Inversion Principle

**Current Vector Database Support**

The pipeline uses `LOVDATA_VECTOR_DB_TYPE` setting to choose the vector database:

- ✅ **ChromaDB** - Fully implemented (only supported option)
  - Supports 3 modes: `memory`, `persistent`, `client`
  - See [USER_GUIDE.md](USER_GUIDE.md#chromadb-setup) for configuration

To add support for other vector databases (Pinecone, Weaviate, Qdrant, etc.):

1. Create a client class implementing the `VectorDBClient` interface (6 abstract methods)
2. Add database-specific settings to `settings.py`
3. Update `PipelineContext.from_settings()` to instantiate your client
4. Test with real credentials

---

### Adding a New Pipeline Step

**1. Create the step function** in `pipeline_steps.py`:

```python
def my_new_step(
    changed_file_paths: list[str],
    force: bool = False
) -> None:
    """My new processing step."""
    settings = Settings()
    logger = logging.getLogger(__name__)

    logger.info(f"Starting my_new_step with {len(changed_file_paths)} files")

    # Your logic here
    for file_path in changed_file_paths:
        try:
            # Process file
            result = process_file(file_path)
            logger.info(f"Processed {file_path}: {result}")
        except Exception as e:
            logger.error(f"Failed to process {file_path}: {e}")

    logger.info("my_new_step completed")
```

**2. Add CLI command** in `cli.py`:

```python
@click.command()
@click.option("--force", is_flag=True, help="Force reprocessing")
def my_step(force: bool) -> None:
    """Run my new step."""
    setup_logging()
    logger = logging.getLogger(__name__)

    try:
        # Get changed files from previous step
        lovlig_client = LovligClient(Settings())
        changed_paths, _ = lovlig_client.get_unprocessed_files()

        # Run step
        my_new_step(changed_paths, force=force)

        logger.info("✓ My step completed successfully")
    except Exception as e:
        logger.error(f"✗ My step failed: {e}")
        raise click.ClickException(str(e))

# Add to CLI group
cli.add_command(my_step)
```

**3. Update full pipeline**:

```python
@click.command()
def full(...):
    """Run complete pipeline."""
    # ... existing steps ...
    ctx.invoke(my_step, force=force)
```

### Adding a New Parser

**1. Create parser class** in `domain/parsers/`:

```python
from lxml import etree
from lovdata_pipeline.domain.models import Article

class MyXMLParser:
    """Parser for my XML format."""

    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.tree = etree.parse(str(file_path))

    def extract_articles(self) -> list[Article]:
        """Extract articles from XML."""
        articles = []
        for elem in self.tree.xpath("//article"):
            article = Article(
                id=elem.get("id"),
                content=elem.text,
                heading=elem.get("heading", ""),
            )
            articles.append(article)
        return articles
```

**2. Use in pipeline step**:

```python
from lovdata_pipeline.domain.parsers.my_parser import MyXMLParser

def chunk_documents(...):
    for file_path in changed_file_paths:
        parser = MyXMLParser(file_path)
        articles = parser.extract_articles()
        # ... chunking logic ...
```

### Adding a New Splitter

**1. Create splitter class** in `domain/splitters/`:

```python
from lovdata_pipeline.domain.models import LegalChunk, Article

class MySplitter:
    """My custom text splitter."""

    def __init__(self, max_tokens: int = 6800):
        self.max_tokens = max_tokens

    def split_article(self, article: Article) -> list[LegalChunk]:
        """Split article into chunks."""
        chunks = []
        # Your splitting logic here
        return chunks
```

**2. Configure in settings**:

```python
# config/settings.py
class Settings(BaseSettings):
    splitter_type: str = "MySplitter"
    splitter_max_tokens: int = 6800
```

---

## Testing

### Test Structure

```
tests/
├── conftest.py              # Shared fixtures
├── unit/                    # Fast, isolated tests
│   ├── models_test.py       # Pydantic model tests
│   ├── splitter_test.py     # Splitter algorithm tests
│   └── token_counter_test.py
├── integration/             # Tests with external systems
│   ├── lovlig_client_test.py
│   ├── chroma_client_test.py
│   └── embedding_test.py
└── end2end/                 # Full pipeline tests
    └── pipeline_test.py
```

### Running Tests

```bash
# Run all tests
make test
# or: uv run pytest

# Run specific test file
uv run pytest tests/unit/models_test.py

# Run with coverage
uv run pytest --cov=lovdata_pipeline

# Run integration tests only
uv run pytest tests/integration/
```

### Writing Tests

**Unit test example:**

```python
# tests/unit/token_counter_test.py

from lovdata_pipeline.domain.splitters.token_counter import TokenCounter

def test_count_tokens():
    """Test token counting."""
    counter = TokenCounter()
    text = "This is a test."
    count = counter.count(text)
    assert count > 0
    assert isinstance(count, int)

def test_count_empty_string():
    """Test token counting with empty string."""
    counter = TokenCounter()
    assert counter.count("") == 0
```

**Integration test example:**

```python
# tests/integration/chroma_client_test.py

import pytest
from lovdata_pipeline.infrastructure.chroma_client import ChromaClient

@pytest.fixture
def chroma_client(tmp_path):
    """Create test ChromaDB client."""
    client = ChromaClient(
        persist_directory=str(tmp_path / "chroma"),
        collection_name="test_collection"
    )
    yield client
    # Cleanup
    client.reset()

def test_upsert_and_query(chroma_client):
    """Test upserting and querying vectors."""
    # Upsert
    chroma_client.upsert(
        ids=["test-1"],
        embeddings=[[0.1, 0.2, 0.3]],
        metadatas=[{"document_id": "test-doc"}]
    )

    # Query
    results = chroma_client.query(
        query_embeddings=[[0.1, 0.2, 0.3]],
        n_results=1
    )

    assert len(results["ids"][0]) == 1
    assert results["ids"][0][0] == "test-1"
```

### Fixtures

Common fixtures in `tests/conftest.py`:

```python
@pytest.fixture
def sample_xml_file(tmp_path):
    """Create sample XML file."""
    xml = """<?xml version="1.0"?>
    <document>
        <article id="1">
            <heading>Test</heading>
            <content>This is test content.</content>
        </article>
    </document>
    """
    file = tmp_path / "test.xml"
    file.write_text(xml)
    return str(file)
```

---

## Development Workflow

### Setting Up Development Environment

```bash
# Clone repo
git clone https://github.com/martgra/lovdata-pipeline.git
cd lovdata-pipeline

# Install dependencies
make install

# Install git hooks
uvx prek install

# Run tests
make test
```

### Development Tools

**Linting and formatting:**

```bash
# Format code
make format
# or: uv run ruff format lovdata_pipeline tests

# Lint code
make lint
# or: uv run ruff check lovdata_pipeline tests

# Auto-fix issues
uv run ruff check --fix lovdata_pipeline tests
```

**Type checking:**

```bash
# Run pylint
uv run pylint lovdata_pipeline
```

**Security scanning:**

```bash
# Scan for secrets
make secrets
# or: uv run detect-secrets scan --baseline .secrets.baseline
```

### Git Workflow

```bash
# Create feature branch
git checkout -b feature/my-feature

# Make changes, commit
git add .
git commit -m "Add my feature"
# Pre-commit hooks run automatically (via Prek)

# Push (runs full test suite)
git push origin feature/my-feature

# Create pull request
# GitHub Actions CI runs automatically
```

### Adding Dependencies

```bash
# Add runtime dependency
uv add package-name

# Add dev dependency
uv add --dev package-name

# Update lock file
uv lock
```

**Never edit `pyproject.toml` directly - always use `uv add`.**

### Dev Container

For reproducible environment:

```bash
# In VS Code: "Dev Containers: Reopen in Container"
# Pre-configured with Python 3.13, uv, and all tools
```

---

## Contributing

### Pull Request Process

1. **Create feature branch** from `main`
2. **Make changes** with tests
3. **Run quality checks** (automatically via Prek)
4. **Push branch** (triggers CI)
5. **Create PR** with description
6. **Address review comments**
7. **Merge** after approval

### Code Style

- Follow PEP 8 (enforced by Ruff)
- Use type hints (checked by Pylint)
- Write docstrings (Google style)
- Keep functions small (<50 lines)
- One responsibility per function

### Documentation

- Update relevant docs for changes
- Add docstrings to new functions
- Include examples in docstrings
- Update README if needed

---

## Performance Optimization

### Profiling

```bash
# Profile pipeline step
python -m cProfile -o profile.stats -m lovdata_pipeline chunk

# View results
python -m pstats profile.stats
# > sort cumtime
# > stats 20
```

### Memory Profiling

```bash
# Install memory profiler
uv add --dev memory-profiler

# Profile function
from memory_profiler import profile

@profile
def my_function():
    ...

# Run
python -m memory_profiler script.py
```

### Optimization Tips

1. **Use streaming** - Process files one at a time
2. **Batch API calls** - Group OpenAI requests
3. **Cache results** - Avoid recomputation
4. **Profile first** - Measure before optimizing
5. **Parallelize** - Use multiprocessing for CPU-bound tasks

---

## Next Steps

- [User Guide](USER_GUIDE.md) - Using the pipeline
- [Functional Requirements](FUNCTIONAL_REQUIREMENTS.md) - Specification
- [Incremental Updates](INCREMENTAL_UPDATES.md) - Change detection logic
