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

**Radical Simplicity:**

- One command does everything
- Atomic per-file processing
- Simple JSON state file
- No orchestration, no stages
- Direct library usage (no abstractions)

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
Pipeline (pipeline.py)
    ↓
Domain Logic (parsers, splitters, models)
    ↓
External Systems (lovlig, OpenAI, ChromaDB)
```

---

## Project Structure

```
lovdata_pipeline/
├── __main__.py              # Entry point
├── cli.py                   # Typer-based CLI (97 lines)
├── pipeline.py              # Atomic processing logic (286 lines)
├── state.py                 # Simple state tracking (91 lines)
├── lovlig.py                # Lovlig library wrapper (108 lines)
│
├── config/
│   └── settings.py          # Environment-based configuration
│
├── domain/
│   ├── models.py            # Pydantic models
│   ├── parsers/
│   │   └── xml_chunker.py   # XML parsing
│   └── splitters/
│       ├── recursive_splitter.py  # Chunking algorithm
│       └── token_counter.py       # Token counting
│
├── infrastructure/
│   └── chroma_client.py     # ChromaDB wrapper (memory/persistent/client modes)
│
└── utils/
    └── file_ops.py          # File utilities

tests/
├── unit/                    # Fast, isolated tests
│   ├── state_test.py
│   ├── lovlig_test.py
│   ├── xml_chunker_test.py
│   ├── recursive_splitter_test.py
│   ├── token_counter_test.py
│   ├── models_test.py
│   └── chroma_modes_test.py
│
└── integration/             # End-to-end tests
    └── pipeline_test.py     # Complete atomic pipeline test
```

### Key Files

| File          | Purpose         | Lines | Why It Exists                     |
| ------------- | --------------- | ----- | --------------------------------- |
| `cli.py`      | CLI interface   | 97    | User commands                     |
| `pipeline.py` | Core processing | 286   | Orchestrates atomic per-file flow |
| `state.py`    | State tracking  | 91    | Tracks processed/failed documents |
| `lovlig.py`   | Lovlig wrapper  | 108   | Syncs files, detects changes      |

**Total core: 582 lines** (down from ~2,882 lines!)

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
    result = run_pipeline(config)
```

### 2. Pipeline Orchestration (`pipeline.py`)

```python
def run_pipeline(config: dict) -> dict:
    """Main pipeline: sync → process each file → cleanup."""

    # 1. Sync files from Lovdata
    lovlig = Lovlig(data_dir, dataset_filter)
    lovlig.sync()

    # 2. Get changed files
    changed_files = lovlig.get_changed_files()
    removed_files = lovlig.get_removed_files()

    # 3. Process each file atomically
    for xml_path in changed_files:
        process_file(xml_path, state, chroma, openai, config)

    # 4. Clean up removed files
    for removal in removed_files:
        state.remove(removal.document_id)
        chroma.delete(removal.document_id)
```

### 3. Per-File Processing (`process_file()`)

```python
def process_file(xml_path, state, chroma, openai, config):
    """Atomic: parse → chunk → embed → index."""

    doc_id = xml_path.stem

    # 1. Parse XML
    articles = extract_articles_from_xml(xml_path)

    # 2. Chunk articles
    chunks = []
    for article in articles:
        chunks.extend(chunk_article(article, doc_id, ...))

    # 3. Embed chunks
    enriched = embed_chunks(chunks, openai, model)

    # 4. Index in ChromaDB
    vector_ids = []
    for chunk in enriched:
        id = chroma.upsert([chunk])
        vector_ids.append(id)

    # 5. Mark as processed
    state.mark_processed(doc_id, file_hash, vector_ids)
```

### 4. State Tracking (`state.py`)

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
def chunk_article(article, ...):
    splitter = CustomSplitter()  # Instead of XMLAwareRecursiveSplitter
    return splitter.split_article(article)
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
    # Replace ChromaClient with PineconeClient
    vector_db = PineconeClient(...)
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
