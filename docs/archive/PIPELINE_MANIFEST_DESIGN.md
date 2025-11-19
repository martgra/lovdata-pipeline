# Pipeline Manifest Design

## Overview

This document defines the formal pipeline manifest schema that tracks the complete processing state of each document version through all pipeline stages.

## Requirements Addressed

- **Req 3**: Local "pipeline manifest" tracking stage completion per (Document ID, hash)
- **Req 6**: Stage model with highest completed stage tracking
- **Req 7**: Per-stage checkpointing with intermediate artifacts
- **Req 8**: Per-document failure recovery
- **Req 21**: Auditability with processing history

## Current State (Before Manifest)

Currently, state is tracked in three separate files:

```
data/
├── state.json              # Lovlig state (file changes)
├── processed_files.json    # Chunking completion timestamps
└── embedded_files.json     # Embedding completion metadata
```

**Limitations:**

- No unified view of document processing state
- Can't see which stage failed for a given document
- No error tracking or retry metadata
- Hard to audit processing history
- No concept of "stage progression"

## Proposed Manifest Schema

### File Structure

```
data/
├── state.json                  # [EXISTING] Lovlig state
├── pipeline_manifest.json      # [NEW] Unified pipeline state
└── manifests/                  # [NEW] Per-document detail files (optional)
    └── {document_id}.json
```

### Core Schema: `pipeline_manifest.json`

```json
{
  "version": "1.0.0",
  "last_updated": "2025-11-19T10:00:00Z",
  "documents": {
    "nl-18840614-003": {
      "document_id": "nl-18840614-003",
      "dataset_name": "gjeldende-lover.tar.bz2",
      "relative_path": "nl/nl-18840614-003.xml",
      "current_version": {
        "file_hash": "abc123...",
        "discovered_at": "2025-11-18T02:32:04Z",
        "file_size_bytes": 12345,
        "stages": {
          "chunking": {
            "status": "completed",
            "started_at": "2025-11-19T08:00:00Z",
            "completed_at": "2025-11-19T08:00:05Z",
            "output": {
              "chunk_count": 45,
              "output_file": "data/chunks/legal_chunks.jsonl",
              "line_range": [1000, 1045]
            },
            "metadata": {
              "splitter": "XMLAwareRecursiveSplitter",
              "max_tokens": 512
            }
          },
          "embedding": {
            "status": "completed",
            "started_at": "2025-11-19T08:05:00Z",
            "completed_at": "2025-11-19T08:05:30Z",
            "output": {
              "chunk_count": 45,
              "output_file": "data/enriched/embedded_chunks.jsonl",
              "line_range": [2000, 2045]
            },
            "metadata": {
              "model_name": "text-embedding-3-small",
              "batch_size": 1000
            }
          },
          "indexing": {
            "status": "completed",
            "started_at": "2025-11-19T08:06:00Z",
            "completed_at": "2025-11-19T08:06:10Z",
            "output": {
              "index_name": "lovdata_index",
              "vector_ids": ["nl-18840614-003::abc123::0", "..."]
            },
            "metadata": {
              "collection": "legal_docs"
            }
          }
        },
        "current_stage": "indexing",
        "index_status": "indexed"
      },
      "version_history": [
        {
          "file_hash": "old_hash_123",
          "processed_at": "2025-11-15T10:00:00Z",
          "index_status": "deleted",
          "deleted_at": "2025-11-19T08:00:00Z"
        }
      ]
    },
    "nl-18880623-003": {
      "document_id": "nl-18880623-003",
      "dataset_name": "gjeldende-lover.tar.bz2",
      "relative_path": "nl/nl-18880623-003.xml",
      "current_version": {
        "file_hash": "def456...",
        "discovered_at": "2025-11-19T09:00:00Z",
        "file_size_bytes": 8900,
        "stages": {
          "chunking": {
            "status": "failed",
            "started_at": "2025-11-19T09:01:00Z",
            "failed_at": "2025-11-19T09:01:03Z",
            "error": {
              "type": "XMLParseError",
              "message": "Invalid XML structure: unclosed tag at line 45",
              "classification": "permanent",
              "traceback": "..."
            },
            "retry_count": 2,
            "last_retry_at": "2025-11-19T09:15:00Z"
          }
        },
        "current_stage": "chunking",
        "index_status": "failed"
      }
    }
  },
  "summary": {
    "total_documents": 1543,
    "by_stage": {
      "not_started": 12,
      "chunking": 5,
      "embedding": 3,
      "indexing": 1,
      "completed": 1520,
      "failed": 2
    },
    "by_index_status": {
      "indexed": 1520,
      "pending": 21,
      "failed": 2
    }
  }
}
```

## Stage Status Values

Each stage can have one of these statuses:

| Status        | Description            | Next Action                       |
| ------------- | ---------------------- | --------------------------------- |
| `not_started` | Stage hasn't begun     | Start processing                  |
| `in_progress` | Currently processing   | Wait or check if stale            |
| `completed`   | Successfully completed | Move to next stage                |
| `failed`      | Encountered error      | Retry or skip based on error type |
| `skipped`     | Intentionally skipped  | Move to next stage                |

## Index Status Values

Document-level index status:

| Status     | Description                      |
| ---------- | -------------------------------- |
| `indexed`  | All vectors in index are current |
| `pending`  | Needs indexing (new or modified) |
| `updating` | Currently being updated          |
| `failed`   | Indexing failed                  |
| `deleted`  | Removed from index               |

## Error Classification

Each error should be classified:

```json
{
  "error": {
    "type": "OpenAIAPIError",
    "message": "Rate limit exceeded",
    "classification": "transient",
    "retry_after": "2025-11-19T09:20:00Z",
    "retry_count": 1,
    "max_retries": 3
  }
}
```

### Error Types

**Transient** (auto-retriable):

- Network errors
- API rate limits
- Temporary service outages
- Lock conflicts

**Permanent** (require manual intervention):

- XML parsing errors
- Invalid file format
- Missing required fields
- Schema validation failures

## API Design

### Reading Manifest

```python
from lovdata_pipeline.infrastructure.pipeline_manifest import PipelineManifest

manifest = PipelineManifest.load()

# Get document state
doc_state = manifest.get_document("nl-18840614-003")
if doc_state:
    current_stage = doc_state.current_version.current_stage
    is_completed = doc_state.current_version.stages["embedding"].status == "completed"

# Find documents needing processing
pending_docs = manifest.get_documents_by_stage_status("chunking", "not_started")
failed_docs = manifest.get_documents_with_status("failed")

# Check what needs indexing
needs_indexing = manifest.get_documents_by_index_status("pending")
```

### Updating Manifest

```python
# Start a stage
manifest.start_stage(
    document_id="nl-18840614-003",
    file_hash="abc123",
    stage="chunking"
)

# Complete a stage
manifest.complete_stage(
    document_id="nl-18840614-003",
    file_hash="abc123",
    stage="chunking",
    output={
        "chunk_count": 45,
        "output_file": "data/chunks/legal_chunks.jsonl"
    },
    metadata={"splitter": "XMLAwareRecursiveSplitter"}
)

# Record failure
manifest.fail_stage(
    document_id="nl-18840614-003",
    file_hash="abc123",
    stage="embedding",
    error_type="OpenAIAPIError",
    error_message="Rate limit exceeded",
    classification="transient"
)

# Update index status
manifest.set_index_status(
    document_id="nl-18840614-003",
    status="indexed"
)
```

## Migration Plan

### Phase 1: Create Manifest Infrastructure

1. Create `PipelineManifest` class
2. Implement schema and persistence
3. Add migration utility to import from existing state files

### Phase 2: Integrate with Existing Assets

1. Update `chunk_documents` to use manifest
2. Update `enrich_documents` to use manifest
3. Keep existing state files temporarily for backward compatibility

### Phase 3: Add New Features

1. Implement error classification
2. Add retry logic
3. Create indexing asset with manifest support

### Phase 4: Deprecate Old State Files

1. Remove `processed_files.json` logic
2. Remove `embedded_files.json` logic
3. Use only `state.json` (lovlig) + `pipeline_manifest.json`

## Benefits

1. **Single Source of Truth**: One file to check document processing state
2. **Auditability**: Complete history of what happened to each document
3. **Recovery**: Know exactly which stage failed and why
4. **Observability**: Easy to generate reports and dashboards
5. **Error Handling**: Distinguish transient vs permanent failures
6. **Testing**: Easy to mock and verify state transitions

## Backward Compatibility

During migration:

- Read from both old and new state files
- Write to both old and new state files
- Provide migration script to convert existing state
- Gradually deprecate old files over several releases

## Future Enhancements

1. **Per-document detail files** in `manifests/{doc_id}.json` for large corpora
2. **Event log** with append-only audit trail
3. **Metrics aggregation** for monitoring dashboards
4. **State compression** for archiving old versions
5. **Distributed locking** for parallel processing
