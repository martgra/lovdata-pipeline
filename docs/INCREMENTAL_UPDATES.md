# Incremental Updates Implementation

## Overview

The pipeline now supports incremental processing, allowing it to:

- Skip reprocessing unchanged files
- Rechunk only modified files
- **Automatically remove chunks for deleted files**
- Handle removed files appropriately
- Recover from failures without reprocessing everything

## Key Components

### 1. Separate Processing State

The system maintains **two separate state files**:

- **`state.json`** - Managed by lovlig library
  - Completely regenerated on every sync
  - Contains file metadata (paths, sizes, hashes, timestamps)
  - Never contains custom processing state
- **`processed_files.json`** - Managed by our pipeline
  - Independent of lovlig's state management
  - Tracks when each file was last processed
  - Survives across lovlig sync operations
  - Structure: `{dataset_name: {file_path: processed_at_timestamp}}`

**Why separate?** The lovlig library's `StateManager.__exit__()` completely regenerates `state.json` on every sync, wiping any custom fields. A separate file ensures processing state persists.

### 2. Timestamp-Based Comparison

Files are identified as needing reprocessing using:

```python
file needs processing IF:
  - file.last_changed > processed_at OR
  - no processed_at exists for the file
```

This comparison happens in `LovligClient.get_unprocessed_files()`.

### 3. Incremental Chunking

When a file is modified:

1. **Remove old chunks** - `ChunkWriter.remove_chunks_for_document(document_id)` filters out all chunks for that document
2. **Write new chunks** - Process the file and append new chunks
3. **Mark as processed** - Update `processed_files.json` with current timestamp

**Critical ordering**: Old chunks must be removed BEFORE opening the ChunkWriter for appending, to avoid file handle conflicts.

### 4. Removed File Handling

When files are removed from the dataset:

1. **Clean processing state** - `LovligClient.clean_removed_files_from_processed_state()` removes entries for deleted files
2. **Remove chunks automatically** - Chunks are deleted in the same chunking asset run
3. **Identify removed** - `LovligClient.get_removed_files()` returns list of removed files

## Implementation Pattern

### In Chunking Asset

```python
# Get files that need processing (modified or added)
changed_files = lovlig.get_unprocessed_files(force_reprocess=False)

# Get removed files for cleanup
removed_files = lovlig.get_removed_files()

writer = ChunkWriter(chunks_file)

# First pass: Remove old chunks
# Pass 1A: Remove chunks for deleted files
for removal in removed_files:
    removed_chunks = writer.remove_chunks_for_document(removal.document_id)
    if removed_chunks > 0:
        context.log.info(f"Removed {removed_chunks} chunks for deleted file {removal.document_id}")

# Pass 1B: Remove chunks for modified documents
for file_path in changed_file_paths:
    document_id = Path(file_path).stem
    removed_chunks = writer.remove_chunks_for_document(document_id)
    if removed_chunks > 0:
        context.log.info(f"Removed {removed_chunks} old chunks for {document_id}")

# Second pass: Process files and write new chunks
with writer:
    for file_path in changed_file_paths:
        # Parse, chunk, and write
        chunks = process_file(file_path)
        writer.write_chunks(chunks)

        # Mark as processed
        lovlig.mark_file_processed(dataset_name, relative_path)
```

### In Ingestion Asset

```python
# After sync completes
lovlig.clean_removed_files_from_processed_state()

# Get removed files (returned for downstream use)
removed_files = lovlig.get_removed_files()
# Passed to chunking asset for automatic cleanup
```

## Testing

Comprehensive integration tests in `tests/integration/test_incremental_updates.py`:

### Test 1: Full Update Cycle

- **Setup**: Initial load with 3 documents
- **Update**: Modify 1, remove 1, add 1
- **Verify**:
  - Only 2 files reprocessed (modified + added)
  - Unchanged file skipped
  - Modified file's old chunks removed
  - Removed file's chunks automatically deleted
  - Processing state correct

### Test 2: Multiple Modifications

- **Setup**: Single document
- **Updates**: Modify 3 times in succession
- **Verify**:
  - Each update removes old version
  - Only latest version remains
  - Processing state tracks correctly

## Benefits

1. **Performance** - Skip reprocessing unchanged files (potentially thousands)
2. **Recovery** - Resume from failures without starting over
3. **Correctness** - Modified files don't create duplicate chunks
4. **Automatic Cleanup** - Deleted files have their chunks removed automatically
5. **Synchronization** - Output file always reflects current dataset state

## Future Enhancements

- **Downstream propagation** - Track which chunks need re-embedding
- **Parallel processing** - Process multiple files concurrently
- **Batch updates** - Group multiple modifications for efficiency
- **State versioning** - Handle schema changes in processing state

## Usage

The incremental processing is **automatic** - just run the pipeline as normal:

```bash
# First run: processes all files
uv run dagster asset materialize --select lovdata_chunks

# Subsequent runs: only processes changed files
uv run dagster asset materialize --select lovdata_chunks

# Force reprocessing if needed
uv run dagster asset materialize --select lovdata_chunks -c force_reprocess=true
```

## Troubleshooting

**Files not being reprocessed?**

- Check timestamps in `processed_files.json`
- Compare with `last_changed` in `state.json`
- Verify timezone handling (all timestamps use UTC)

**Old chunks not removed?**

- Ensure `remove_chunks_for_document` is called before opening writer
- Check document_id extraction matches chunk document_id
- Verify both deleted and modified files are handled in Pass 1A and 1B

**Processing state lost?**

- Verify `processed_files.json` exists alongside `state.json`
- Check file permissions
- Look for errors in lovlig client logs
