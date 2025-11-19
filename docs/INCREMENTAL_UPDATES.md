# Incremental Updates

How the pipeline detects and handles changed files.

## Overview

The pipeline tracks processed documents to avoid reprocessing unchanged files:

- **Lovlig library** - Syncs files from Lovdata, detects changes via xxHash
- **State file** - Tracks processed documents with hashes
- **Atomic processing** - Changed files processed fully (parse → embed → index)
- **Automatic cleanup** - Removed/modified files cleaned from index

## How It Works

### 1. Lovlig Detects Changes

The lovlig library syncs files and creates `data/state.json`:

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

**Status values:**
- `added` - New file
- `modified` - Content changed (hash differs)
- `removed` - File deleted
- `unchanged` - No changes

### 2. Pipeline Tracks Processing

The pipeline maintains `data/pipeline_state.json`:

```json
{
  "processed": {
    "nl-18840614-003": {
      "hash": "abc123...",
      "vectors": ["vec_id_1", "vec_id_2", "vec_id_3"],
      "timestamp": "2025-11-19T10:30:00Z"
    }
  },
  "failed": {
    "nl-19010101-999": {
      "hash": "def456...",
      "error": "Invalid XML structure",
      "timestamp": "2025-11-19T10:35:00Z"
    }
  }
}
```

### 3. Change Detection Logic

```python
def needs_processing(doc_id: str, current_hash: str) -> bool:
    """Check if document needs processing."""
    
    # Not processed yet
    if doc_id not in state.processed:
        return True
    
    # Hash changed (content modified)
    if state.processed[doc_id]["hash"] != current_hash:
        return True
    
    # Previously failed (retry)
    if doc_id in state.failed:
        return True
    
    return False
```

### 4. Processing Flow

```python
def run_pipeline(config):
    # 1. Sync from Lovdata
    lovlig.sync()
    
    # 2. Get changed files
    changed = lovlig.get_changed_files()    # added + modified
    removed = lovlig.get_removed_files()    # deleted
    
    # 3. Process changed files
    for xml_path in changed:
        doc_id = xml_path.stem
        file_hash = lovlig.get_hash(xml_path)
        
        # Skip if already processed with same hash
        if state.is_processed(doc_id, file_hash):
            continue
        
        # Remove old vectors if modified
        if doc_id in state.processed:
            old_vectors = state.get_vectors(doc_id)
            chroma.delete_by_ids(old_vectors)
        
        # Process file atomically
        articles = parse_xml(xml_path)
        chunks = chunk_articles(articles)
        enriched = embed_chunks(chunks)
        vector_ids = index_chunks(enriched)
        
        # Mark as processed
        state.mark_processed(doc_id, file_hash, vector_ids)
    
    # 4. Clean up removed files
    for removal in removed:
        old_vectors = state.get_vectors(removal.document_id)
        chroma.delete_by_ids(old_vectors)
        state.remove(removal.document_id)
```

## Implementation Details

### State Module (`state.py`)

Simple JSON-based state tracking:

```python
class ProcessingState:
    """Track processed and failed documents."""
    
    def __init__(self, path: Path):
        self.path = path
        self.data = self._load()
    
    def mark_processed(self, doc_id: str, hash: str, vectors: list):
        """Record successful processing."""
        self.data["processed"][doc_id] = {
            "hash": hash,
            "vectors": vectors,
            "timestamp": datetime.now(UTC).isoformat()
        }
        self._save()
    
    def mark_failed(self, doc_id: str, hash: str, error: str):
        """Record processing failure."""
        self.data["failed"][doc_id] = {
            "hash": hash,
            "error": error,
            "timestamp": datetime.now(UTC).isoformat()
        }
        self._save()
    
    def is_processed(self, doc_id: str, hash: str) -> bool:
        """Check if document already processed with this hash."""
        entry = self.data["processed"].get(doc_id)
        return entry is not None and entry["hash"] == hash
    
    def get_vectors(self, doc_id: str) -> list[str]:
        """Get vector IDs for document."""
        entry = self.data["processed"].get(doc_id)
        return entry["vectors"] if entry else []
    
    def remove(self, doc_id: str):
        """Remove document from state."""
        self.data["processed"].pop(doc_id, None)
        self.data["failed"].pop(doc_id, None)
        self._save()
```

### Lovlig Wrapper (`lovlig.py`)

Wraps lovlig library for change detection:

```python
class Lovlig:
    """Wrapper around lovlig library."""
    
    def sync(self):
        """Sync files from Lovdata."""
        from lovdata_processing import sync_datasets
        sync_datasets(
            dataset_filter=self.dataset_filter,
            raw_data_dir=self.raw_dir,
            extracted_data_dir=self.extracted_dir,
            state_file=self.state_file
        )
    
    def get_changed_files(self) -> list[FileChange]:
        """Get added and modified files."""
        state = self._read_state()
        changed = []
        
        for file_info in state["files"]:
            if file_info["status"] in ["added", "modified"]:
                changed.append(FileChange(
                    relative_path=file_info["relative_path"],
                    document_id=Path(file_info["relative_path"]).stem,
                    hash=file_info["hash"],
                    status=file_info["status"]
                ))
        
        return changed
    
    def get_removed_files(self) -> list[FileChange]:
        """Get deleted files."""
        state = self._read_state()
        removed = []
        
        for file_info in state["files"]:
            if file_info["status"] == "removed":
                removed.append(FileChange(
                    relative_path=file_info["relative_path"],
                    document_id=Path(file_info["relative_path"]).stem,
                    hash=file_info.get("hash", ""),
                    status="removed"
                ))
        
        return removed
```

## Benefits

### 1. Performance

Only process changed files:

```
First run: 3,000 files → ~30 minutes
Update with 10 changes: 10 files → ~1 minute
```

### 2. Correctness

Modified files:
- Old vectors automatically deleted
- New vectors indexed
- No duplicates in index

### 3. Recovery

Pipeline crashes:
- State persists to disk
- Restart skips processed files
- Only processes remaining files

### 4. Observability

Track what's happened:

```bash
# View processed documents
jq '.processed | length' data/pipeline_state.json

# View failed documents
jq '.failed | keys' data/pipeline_state.json

# Check specific document
jq '.processed["nl-18840614-003"]' data/pipeline_state.json
```

## Example Scenarios

### Scenario 1: Initial Load

```
lovlig sync → 3,000 new files
pipeline → processes all 3,000 files
state → marks all 3,000 as processed
```

### Scenario 2: Incremental Update

```
lovlig sync → 10 modified, 2 new, 1 removed
pipeline → 
  - removes old vectors for 10 modified
  - processes 12 files (10 modified + 2 new)
  - removes vectors for 1 deleted
state → updates 12 entries, removes 1
```

### Scenario 3: Pipeline Crash

```
First run: 1,000 files processed, crash at file 1,001
state → contains 1,000 processed documents

Restart:
pipeline → skips 1,000 processed, continues from 1,001
```

### Scenario 4: Force Reprocess

```
User runs: --force
pipeline → ignores state, reprocesses all files
state → overwrites all entries with new vectors
```

## Testing

Comprehensive tests in `tests/unit/state_test.py` and `tests/unit/lovlig_test.py`:

```python
def test_incremental_processing():
    """Test that only changed files are processed."""
    
    # Initial load
    state.mark_processed("doc1", "hash1", ["vec1"])
    state.mark_processed("doc2", "hash2", ["vec2"])
    
    # doc1 modified (hash changed)
    assert not state.is_processed("doc1", "hash1_new")
    
    # doc2 unchanged
    assert state.is_processed("doc2", "hash2")
    
    # doc3 new
    assert not state.is_processed("doc3", "hash3")
```

## Performance Characteristics

| Operation | Time Complexity | Space |
|-----------|----------------|-------|
| Check if processed | O(1) | O(n) documents |
| Mark processed | O(1) | O(1) write |
| Get changed files | O(n) files | O(n) temp |
| Load state | O(n) | O(n) memory |

For 15,000 documents:
- State file: ~5MB
- Load time: <100ms
- Lookup time: <1ms

## Troubleshooting

### State Out of Sync

**Symptom:** Pipeline reprocesses files unnecessarily

**Solution:**
```bash
# Check lovlig state
cat data/state.json | jq '.files[] | select(.status == "modified")'

# Check pipeline state
cat data/pipeline_state.json | jq '.processed | keys'

# Force reprocess if needed
uv run python -m lovdata_pipeline process --force
```

### Corrupted State File

**Symptom:** JSON parse error

**Solution:**
```bash
# Backup (if recoverable)
cp data/pipeline_state.json data/pipeline_state.json.bak

# Delete and reprocess
rm data/pipeline_state.json
uv run python -m lovdata_pipeline process --force
```

### Missing Vectors

**Symptom:** State shows processed but ChromaDB missing vectors

**Solution:**
```bash
# Check ChromaDB
# (requires custom script to query chroma)

# Reprocess affected documents
# (edit state.json to remove entries, or use --force)
```

## Future Enhancements

Potential improvements:

1. **Batch updates** - Group multiple small changes
2. **Parallel processing** - Process multiple files concurrently
3. **State versioning** - Handle schema changes
4. **Backup/restore** - State snapshots
5. **Reconciliation** - Verify state vs ChromaDB

## References

- **[User Guide](USER_GUIDE.md)** - How to use the pipeline
- **[Developer Guide](DEVELOPER_GUIDE.md)** - Architecture details
- **[Functional Requirements](FUNCTIONAL_REQUIREMENTS.md)** - Specification
