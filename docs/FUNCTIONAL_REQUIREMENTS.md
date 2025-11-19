# Functional Requirements

**Status:** ✅ SPECIFICATION  
**Last Updated:** November 19, 2025

> **Purpose:** This document defines the requirements that the pipeline MUST satisfy. All changes should be verified against these requirements.

---

## Table of Contents

1. [Overview](#overview)
2. [Change Detection](#1-change-detection)
3. [Change Handling](#2-change-handling)
4. [Processing](#3-processing)
5. [State Management](#4-state-management)
6. [Index Consistency](#5-index-consistency)
7. [Error Handling](#6-error-handling)
8. [Observability](#7-observability)
9. [Verification Checklist](#verification-checklist)

---

## Overview

The pipeline processes Norwegian legal documents from Lovdata into a vector database, ensuring:

- **Only changed files** are processed (incremental updates)
- **Atomic processing** - each file completes fully (parse → chunk → embed → index)
- **State tracking** - knows what's been processed and with what hash
- **Index consistency** - vectors match current corpus (no orphans, no duplicates)
- **Automatic cleanup** - removes vectors for deleted/modified files

---

## 1. Change Detection

### 1.1 Use lovlig as Source of Truth

**Requirement:**

The pipeline SHALL use the `lovlig` library to:
- Sync files from Lovdata
- Detect added, modified, and removed files
- Provide content hashes (xxHash) for version tracking

**Implementation:** ✅

```python
# lovdata_pipeline/lovlig.py
class Lovlig:
    def sync(self):
        """Sync files from Lovdata using lovlig library."""
        lovlig.sync_datasets(self.dataset_filter, ...)
    
    def get_changed_files(self) -> list[FileChange]:
        """Get added and modified files from lovlig state."""
        # Reads data/state.json created by lovlig
```

**Verification:**
- lovlig library handles all Lovdata interaction
- Pipeline reads lovlig's `state.json` for changes
- No direct ZIP inspection or timestamp comparison

### 1.2 File Identity

**Requirement:**

Each document SHALL be identified by:
- **Document ID** - filename stem (e.g. `nl-18840614-003` from `nl/nl-18840614-003.xml`)
- **Version** - xxHash from lovlig library

**Implementation:** ✅

```python
# Extract document ID from filename
doc_id = xml_path.stem  # "nl-18840614-003"

# Get hash from lovlig state
file_hash = lovlig.get_hash(xml_path)  # xxHash
```

**Verification:**
- Document ID is stable across updates
- Hash changes when content changes
- Same document + different hash = new version

### 1.3 State Tracking

**Requirement:**

The pipeline SHALL maintain state storing:
- Processed documents with hashes
- Vector IDs for each document
- Failed documents with errors
- Timestamps for all entries

**Implementation:** ✅

```python
# lovdata_pipeline/state.py
{
  "processed": {
    "doc_id": {
      "hash": "abc123...",
      "vectors": ["vec_1", "vec_2"],
      "timestamp": "2025-11-19T10:30:00Z"
    }
  },
  "failed": {
    "doc_id": {
      "hash": "def456...",
      "error": "Parse error",
      "timestamp": "2025-11-19T10:35:00Z"
    }
  }
}
```

**Verification:**
- State persists across runs
- Hash comparison determines if reprocessing needed
- Vector IDs enable cleanup

---

## 2. Change Handling

### 2.1 Added Documents

**Requirement:**

For files with status `added`, the pipeline SHALL:
1. Check if already processed with same hash
2. If not processed, run full pipeline: parse → chunk → embed → index
3. Mark as processed with hash and vector IDs

**Implementation:** ✅

```python
def run_pipeline(config):
    changed = lovlig.get_changed_files()  # includes "added"
    
    for file_change in changed:
        if not state.is_processed(file_change.document_id, file_change.hash):
            vectors = process_file(file_change.path, ...)
            state.mark_processed(file_change.document_id, file_change.hash, vectors)
```

**Verification:**
- New files are processed
- Duplicate processing avoided (hash check)
- State updated on success

### 2.2 Modified Documents

**Requirement:**

For files with status `modified`, the pipeline SHALL:
1. Delete old vectors for that document ID
2. Process new version completely
3. Index new vectors
4. Update state with new hash and vector IDs

**Implementation:** ✅

```python
def process_file(xml_path, state, chroma, ...):
    doc_id = xml_path.stem
    
    # Remove old vectors if document was previously processed
    if doc_id in state.processed:
        old_vectors = state.get_vectors(doc_id)
        chroma.delete_by_ids(old_vectors)
    
    # Process new version
    articles = parse_xml(xml_path)
    chunks = chunk_articles(articles)
    enriched = embed_chunks(chunks)
    vector_ids = index_chunks(enriched)
    
    # Update state
    state.mark_processed(doc_id, new_hash, vector_ids)
```

**Verification:**
- Old vectors removed before indexing new
- No duplicate vectors in index
- State reflects latest version

### 2.3 Removed Documents

**Requirement:**

For files with status `removed`, the pipeline SHALL:
1. Delete all vectors for that document ID
2. Remove document from state
3. Log the removal

**Implementation:** ✅

```python
def run_pipeline(config):
    removed = lovlig.get_removed_files()
    
    for removal in removed:
        # Delete vectors
        old_vectors = state.get_vectors(removal.document_id)
        if old_vectors:
            chroma.delete_by_ids(old_vectors)
        
        # Remove from state
        state.remove(removal.document_id)
        
        logger.info(f"Removed {len(old_vectors)} vectors for {removal.document_id}")
```

**Verification:**
- Vectors deleted from ChromaDB
- State cleaned up
- No orphaned vectors remain

---

## 3. Processing

### 3.1 Atomic Per-File Processing

**Requirement:**

Each file SHALL be processed atomically:
1. Parse XML → Extract articles
2. Chunk articles → Create text chunks
3. Embed chunks → Generate vectors (OpenAI)
4. Index vectors → Store in ChromaDB

No file proceeds to step N+1 until step N completes.

**Implementation:** ✅

```python
def process_file(xml_path, state, chroma, openai, config):
    """Atomic processing: parse → chunk → embed → index."""
    
    # 1. Parse
    articles = extract_articles_from_xml(xml_path)
    
    # 2. Chunk
    chunks = []
    for article in articles:
        chunks.extend(chunk_article(article, ...))
    
    # 3. Embed
    enriched = embed_chunks(chunks, openai, model)
    
    # 4. Index
    vector_ids = []
    for chunk in enriched:
        id = chroma.upsert([chunk])
        vector_ids.append(id)
    
    return vector_ids
```

**Verification:**
- No intermediate files created
- File either fully processed or not at all
- Failure in any step stops processing for that file

### 3.2 Batch Embedding

**Requirement:**

Embedding requests SHALL be batched to:
- Reduce API calls
- Improve throughput
- Respect rate limits

**Implementation:** ✅

```python
def embed_chunks(chunks, openai_client, model):
    """Embed chunks in batches of 100."""
    batch_size = 100
    
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        texts = [c.text for c in batch]
        
        response = openai_client.embeddings.create(input=texts, model=model)
        embeddings = [item.embedding for item in response.data]
        
        # Pair chunks with embeddings
        ...
```

**Verification:**
- Max 100 texts per API call
- Embeddings correctly matched to chunks
- Batching reduces total API calls

### 3.3 Idempotency

**Requirement:**

Running the pipeline multiple times with no changes SHALL:
- Not reprocess any files
- Not create duplicate vectors
- Complete quickly (no-op)

**Implementation:** ✅

```python
def run_pipeline(config):
    changed = lovlig.get_changed_files()
    
    for file_change in changed:
        # Skip if already processed with this hash
        if state.is_processed(file_change.document_id, file_change.hash):
            logger.debug(f"Skipping {file_change.document_id} (already processed)")
            continue
        
        process_file(...)
```

**Verification:**
- Hash comparison prevents reprocessing
- No duplicate vectors created
- Second run completes in <1 minute

---

## 4. State Management

### 4.1 Persistence

**Requirement:**

State SHALL:
- Persist to disk as JSON
- Survive process crashes
- Be human-readable

**Implementation:** ✅

```python
# lovdata_pipeline/state.py
class ProcessingState:
    def _save(self):
        """Save state to disk."""
        with self.path.open("w") as f:
            json.dump(self.data, f, indent=2)
```

**Verification:**
- State file: `data/pipeline_state.json`
- Written after each document processed
- Valid JSON, can inspect with `jq`

### 4.2 Atomic Updates

**Requirement:**

State updates SHALL be atomic:
- Write complete or not at all
- No partial writes
- No corruption on crash

**Implementation:** ✅

```python
def _save(self):
    """Atomic write using temp file + rename."""
    tmp_path = self.path.with_suffix(".tmp")
    with tmp_path.open("w") as f:
        json.dump(self.data, f, indent=2)
    tmp_path.rename(self.path)  # Atomic on POSIX
```

**Verification:**
- Write to temp file first
- Rename (atomic operation)
- No corrupted state files

### 4.3 Statistics

**Requirement:**

State SHALL provide statistics:
- Number of processed documents
- Number of failed documents
- Total vectors indexed

**Implementation:** ✅

```python
def stats(self) -> dict:
    """Get statistics."""
    return {
        "processed": len(self.data["processed"]),
        "failed": len(self.data["failed"]),
        "total_vectors": sum(
            len(entry["vectors"]) 
            for entry in self.data["processed"].values()
        )
    }
```

**Verification:**
- `status` command shows stats
- Accurate counts
- Useful for monitoring

---

## 5. Index Consistency

### 5.1 No Orphaned Vectors

**Requirement:**

The index SHALL NOT contain vectors for documents that:
- Have been removed from the corpus
- Have been modified (old versions)

**Implementation:** ✅

```python
# On modification
if doc_id in state.processed:
    old_vectors = state.get_vectors(doc_id)
    chroma.delete_by_ids(old_vectors)

# On removal
removed = lovlig.get_removed_files()
for removal in removed:
    old_vectors = state.get_vectors(removal.document_id)
    chroma.delete_by_ids(old_vectors)
```

**Verification:**
- Old vectors deleted before indexing new
- Removed documents cleaned from index
- State tracks all vector IDs for cleanup

### 5.2 No Duplicate Vectors

**Requirement:**

The index SHALL NOT contain multiple vectors for the same chunk.

**Implementation:** ✅

Enforced by:
1. Atomic processing (file completes fully or not at all)
2. Hash-based skip (don't reprocess same version)
3. Old vector deletion (clean before indexing new)

**Verification:**
- Each chunk has unique ID in ChromaDB
- Reprocessing removes old first
- Idempotency prevents duplicates

### 5.3 Metadata Consistency

**Requirement:**

Vector metadata SHALL match source document:
- Document ID
- Chunk index
- Section heading
- Lovdata URL

**Implementation:** ✅

```python
class ChunkMetadata(BaseModel):
    document_id: str           # From filename
    chunk_index: int           # 0-based
    section_heading: str       # From XML
    absolute_address: str      # Lovdata URL
    # ... other fields
```

**Verification:**
- Metadata extracted from XML
- Stored with vector in ChromaDB
- Queryable for filtering/retrieval

---

## 6. Error Handling

### 6.1 Per-File Isolation

**Requirement:**

Processing SHALL continue on error:
- Failed file logged
- Failed file marked in state
- Other files processed normally

**Implementation:** ✅

```python
def run_pipeline(config):
    for file_change in changed:
        try:
            vectors = process_file(file_change.path, ...)
            state.mark_processed(file_change.document_id, file_change.hash, vectors)
        except Exception as e:
            logger.error(f"Failed to process {file_change.document_id}: {e}")
            state.mark_failed(file_change.document_id, file_change.hash, str(e))
            continue  # Process next file
```

**Verification:**
- One failure doesn't stop pipeline
- Failed documents in `state.failed`
- Successful documents in `state.processed`

### 6.2 Retry on Rerun

**Requirement:**

Failed documents SHALL be retried on next run.

**Implementation:** ✅

```python
def needs_processing(doc_id, hash):
    """Check if needs processing."""
    # Retry if failed
    if doc_id in state.failed:
        return True
    
    # ... other checks
```

**Verification:**
- Failed documents reprocessed on next run
- Success removes from `failed` section
- Persistent failures remain logged

### 6.3 Graceful Shutdown

**Requirement:**

Pipeline SHALL handle interruption:
- State saved up to last completed file
- Restart resumes from next file
- No corrupted state

**Implementation:** ✅

- State saved after each document
- Atomic writes prevent corruption
- Hash check skips completed files

**Verification:**
- Ctrl+C during run
- Restart pipeline
- Skips completed files, continues from next

---

## 7. Observability

### 7.1 Progress Logging

**Requirement:**

Pipeline SHALL log:
- Number of files to process
- Current file being processed
- Per-file statistics (chunks, vectors)
- Final summary

**Implementation:** ✅

```python
logger.info(f"Processing {len(changed)} changed files...")
logger.info(f"[{i}/{total}] {doc_id}: {len(chunks)} chunks → embedded → indexed ({len(vectors)} vectors)")
logger.info(f"Complete! Processed: {processed}, Failed: {failed}")
```

**Verification:**
- Detailed progress during run
- Per-file statistics
- Summary at end

### 7.2 Status Command

**Requirement:**

Pipeline SHALL provide status command showing:
- Processed document count
- Failed document count
- Total vectors indexed

**Implementation:** ✅

```bash
uv run python -m lovdata_pipeline status

# Output:
# Pipeline Status
#   Processed: 3,000 documents
#   Failed: 2 documents
#   Indexed: 45,000 vectors
```

**Verification:**
- `status` command exists
- Shows accurate counts
- Fast response (<1 second)

### 7.3 State Inspection

**Requirement:**

State file SHALL be human-readable and inspectable.

**Implementation:** ✅

```bash
# View all processed
jq '.processed | keys' data/pipeline_state.json

# View specific document
jq '.processed["nl-18840614-003"]' data/pipeline_state.json

# Count vectors
jq '[.processed[].vectors | length] | add' data/pipeline_state.json
```

**Verification:**
- Valid JSON format
- Pretty-printed (indented)
- Queryable with standard tools

---

## Verification Checklist

Use this checklist when making changes:

### Change Detection
- [ ] Pipeline uses lovlig library for sync
- [ ] Changes detected via `state.json`
- [ ] Document ID stable across updates
- [ ] Hash used for version tracking

### Processing
- [ ] Added files processed completely
- [ ] Modified files: old vectors deleted, new vectors indexed
- [ ] Removed files: vectors deleted, state cleaned
- [ ] Atomic per-file processing (no intermediate files)
- [ ] Batch embedding (100 per request)

### State Management
- [ ] State persists to disk (JSON)
- [ ] State survives crashes
- [ ] Atomic state updates
- [ ] Hash check prevents reprocessing
- [ ] Statistics available

### Index Consistency
- [ ] No orphaned vectors (removed docs cleaned)
- [ ] No duplicate vectors (idempotency)
- [ ] Metadata matches source documents

### Error Handling
- [ ] Failed file doesn't stop pipeline
- [ ] Failed files logged and retryable
- [ ] Graceful shutdown preserves state

### Observability
- [ ] Progress logging during run
- [ ] Status command shows statistics
- [ ] State file human-readable

---

## References

- **[User Guide](USER_GUIDE.md)** - How to use the pipeline
- **[Developer Guide](DEVELOPER_GUIDE.md)** - Architecture details
- **[Incremental Updates](INCREMENTAL_UPDATES.md)** - Change detection implementation
- **[Quick Reference](QUICK_REFERENCE.md)** - Command cheat sheet
