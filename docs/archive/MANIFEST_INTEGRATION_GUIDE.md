# Integration Guide: Adding Manifest to Existing Assets

This guide shows how to integrate the new `PipelineManifest` into the existing chunking and enrichment assets while maintaining backward compatibility.

## Overview

**Goal**: Update existing assets to use the unified manifest while keeping the current state files as a backup during migration.

**Strategy**:

- Write to **both** old state files and new manifest (dual-write)
- Read from manifest first, fall back to old files
- Gradually deprecate old files after validation

## Step 1: Update Chunking Asset

### Before (Current)

```python
# lovdata_pipeline/assets/chunking.py

@dg.asset(...)
def legal_document_chunks(...):
    # ... process files ...

    for file_path in changed_file_paths:
        try:
            # Chunk the file
            chunks = chunker.process(file_path)

            # Mark as processed (old way)
            lovlig.mark_file_processed(dataset_name, relative_file_path)

        except Exception as e:
            context.log.error(f"Failed: {e}")
```

### After (With Manifest)

```python
# lovdata_pipeline/assets/chunking.py

from lovdata_pipeline.infrastructure.pipeline_manifest import (
    PipelineManifest,
    ErrorClassification,
)

@dg.asset(...)
def legal_document_chunks(...):
    manifest = PipelineManifest.load()

    for file_path in changed_file_paths:
        doc_id = Path(file_path).stem

        # Get file metadata
        file_meta = lovlig.get_file_metadata({"path": file_path, ...})

        # Ensure document in manifest
        manifest.ensure_document(
            document_id=doc_id,
            dataset_name=file_meta.dataset_name,
            relative_path=file_meta.relative_path,
            file_hash=file_meta.file_hash,
            file_size_bytes=file_meta.file_size_bytes,
        )

        # Start stage
        manifest.start_stage(doc_id, file_meta.file_hash, "chunking")

        try:
            # Chunk the file
            chunks = chunker.process(file_path)

            # Write chunks...

            # Complete stage (NEW)
            manifest.complete_stage(
                document_id=doc_id,
                file_hash=file_meta.file_hash,
                stage="chunking",
                output={
                    "chunk_count": len(chunks),
                    "output_file": str(settings.chunk_output_path),
                },
                metadata={
                    "splitter": "XMLAwareRecursiveSplitter",
                    "max_tokens": settings.chunk_max_tokens,
                },
            )

            # Mark as processed (OLD - keep for backward compat)
            lovlig.mark_file_processed(dataset_name, relative_file_path)

        except XMLParseError as e:
            # Permanent error
            manifest.fail_stage(
                document_id=doc_id,
                file_hash=file_meta.file_hash,
                stage="chunking",
                error_type="XMLParseError",
                error_message=str(e),
                classification=ErrorClassification.PERMANENT,
                traceback=traceback.format_exc(),
            )
            context.log.error(f"Permanent failure for {doc_id}: {e}")

        except Exception as e:
            # Transient error
            manifest.fail_stage(
                document_id=doc_id,
                file_hash=file_meta.file_hash,
                stage="chunking",
                error_type=type(e).__name__,
                error_message=str(e),
                classification=ErrorClassification.TRANSIENT,
                traceback=traceback.format_exc(),
            )
            context.log.warning(f"Transient failure for {doc_id}: {e}")

    # Save manifest
    manifest.save()

    return MaterializeResult(...)
```

## Step 2: Update Enrichment Asset

### Before (Current)

```python
# lovdata_pipeline/assets/enrichment.py

@dg.asset(...)
def enriched_chunks(...):
    files_to_embed = embedding.get_files_needing_embedding(changed_file_paths)

    for file_path in files_to_embed:
        # Embed chunks...

        # Mark as embedded (old way)
        embedding.mark_file_embedded(
            dataset_name, file_path, file_hash, chunk_count, model_name
        )
```

### After (With Manifest)

```python
# lovdata_pipeline/assets/enrichment.py

from lovdata_pipeline.infrastructure.pipeline_manifest import (
    PipelineManifest,
    ErrorClassification,
    StageStatus,
)

@dg.asset(...)
def enriched_chunks(...):
    manifest = PipelineManifest.load()

    # Get files that need embedding (check manifest first)
    files_to_embed = _get_files_needing_embedding(manifest, changed_file_paths)

    for file_path in files_to_embed:
        doc_id = Path(file_path).stem
        doc = manifest.get_document(doc_id)

        if not doc:
            context.log.warning(f"Document {doc_id} not in manifest, skipping")
            continue

        # Start stage
        manifest.start_stage(doc_id, doc.current_version.file_hash, "embedding")

        try:
            # Read chunks for this document
            chunks = chunk_reader.get_chunks_for_document(doc_id)

            # Embed chunks
            texts = [c["text"] for c in chunks]
            embeddings = embedding.embed_batch(texts)

            # Write enriched chunks...

            # Complete stage (NEW)
            manifest.complete_stage(
                document_id=doc_id,
                file_hash=doc.current_version.file_hash,
                stage="embedding",
                output={
                    "chunk_count": len(chunks),
                    "output_file": str(output_file),
                },
                metadata={
                    "model_name": settings.embedding_model,
                    "batch_size": settings.embedding_batch_size,
                },
            )

            # Mark as embedded (OLD - keep for backward compat)
            embedding.mark_file_embedded(
                dataset_name, file_path, file_hash, len(chunks), model_name
            )

        except OpenAIAPIError as e:
            # Check if rate limit or other transient error
            classification = _classify_openai_error(e)

            manifest.fail_stage(
                document_id=doc_id,
                file_hash=doc.current_version.file_hash,
                stage="embedding",
                error_type="OpenAIAPIError",
                error_message=str(e),
                classification=classification,
                retry_after=_extract_retry_after(e) if classification == ErrorClassification.TRANSIENT else None,
            )

        except Exception as e:
            # Generic error - assume transient
            manifest.fail_stage(
                document_id=doc_id,
                file_hash=doc.current_version.file_hash,
                stage="embedding",
                error_type=type(e).__name__,
                error_message=str(e),
                classification=ErrorClassification.TRANSIENT,
            )

    # Save manifest
    manifest.save()

    return MaterializeResult(...)


def _get_files_needing_embedding(manifest: PipelineManifest, changed_files: list[str]) -> list[str]:
    """Get files that need embedding based on manifest state."""
    result = []

    for file_path in changed_files:
        doc_id = Path(file_path).stem
        doc = manifest.get_document(doc_id)

        if not doc:
            # New document - needs embedding
            result.append(file_path)
            continue

        # Check if chunking completed
        chunking = doc.current_version.stages.get("chunking")
        if not chunking or chunking.status != StageStatus.COMPLETED:
            # Chunking not done yet - skip
            continue

        # Check if embedding already completed
        embedding = doc.current_version.stages.get("embedding")
        if embedding and embedding.status == StageStatus.COMPLETED:
            # Already embedded - skip
            continue

        # Needs embedding
        result.append(file_path)

    return result


def _classify_openai_error(error: Exception) -> ErrorClassification:
    """Classify OpenAI API errors."""
    error_message = str(error).lower()

    if "rate limit" in error_message or "429" in error_message:
        return ErrorClassification.TRANSIENT

    if "timeout" in error_message or "503" in error_message:
        return ErrorClassification.TRANSIENT

    if "invalid" in error_message or "400" in error_message:
        return ErrorClassification.PERMANENT

    # Default to transient
    return ErrorClassification.TRANSIENT


def _extract_retry_after(error: Exception) -> str | None:
    """Extract retry-after timestamp from OpenAI error if available."""
    # TODO: Parse error response headers for Retry-After
    # For now, return None
    return None
```

## Step 3: Update Change Detection

The `changed_file_paths` asset should also consider manifest state:

```python
# lovdata_pipeline/assets/ingestion.py

@dg.asset(...)
def changed_file_paths(...) -> list[str]:
    manifest = PipelineManifest.load()

    # Get files from lovlig
    changed_files = lovlig.get_changed_files()

    result = []
    for file_meta in changed_files:
        doc_id = file_meta.document_id

        # Ensure document in manifest
        manifest.ensure_document(
            document_id=doc_id,
            dataset_name=file_meta.dataset_name,
            relative_path=file_meta.relative_path,
            file_hash=file_meta.file_hash,
            file_size_bytes=file_meta.file_size_bytes,
        )

        result.append(str(file_meta.absolute_path))

    manifest.save()

    return result
```

## Step 4: Add Helper Functions

Create utility functions for common patterns:

```python
# lovdata_pipeline/infrastructure/manifest_helpers.py

from pathlib import Path
from lovdata_pipeline.infrastructure.pipeline_manifest import (
    PipelineManifest,
    ErrorClassification,
)
import traceback


def with_manifest_tracking(stage: str):
    """Decorator to add manifest tracking to a processing function.

    Usage:
        @with_manifest_tracking("chunking")
        def process_document(doc_id, file_hash, file_path, manifest):
            # Process the document
            return {"chunk_count": 45}
    """
    def decorator(func):
        def wrapper(doc_id, file_hash, file_path, manifest, *args, **kwargs):
            # Start stage
            manifest.start_stage(doc_id, file_hash, stage)

            try:
                # Call function
                result = func(doc_id, file_hash, file_path, manifest, *args, **kwargs)

                # Complete stage
                manifest.complete_stage(
                    document_id=doc_id,
                    file_hash=file_hash,
                    stage=stage,
                    output=result.get("output", {}),
                    metadata=result.get("metadata", {}),
                )

                return result

            except Exception as e:
                # Classify error
                classification = classify_error(e)

                # Fail stage
                manifest.fail_stage(
                    document_id=doc_id,
                    file_hash=file_hash,
                    stage=stage,
                    error_type=type(e).__name__,
                    error_message=str(e),
                    classification=classification,
                    traceback=traceback.format_exc(),
                )

                raise

        return wrapper
    return decorator


def classify_error(error: Exception) -> ErrorClassification:
    """Classify an error as transient or permanent."""
    error_type = type(error).__name__
    error_message = str(error).lower()

    # Transient patterns
    transient_patterns = [
        "timeout", "connection", "network", "rate limit",
        "503", "502", "429", "unavailable", "temporary"
    ]

    if any(p in error_message for p in transient_patterns):
        return ErrorClassification.TRANSIENT

    if error_type in ["TimeoutError", "ConnectionError", "HTTPError"]:
        return ErrorClassification.TRANSIENT

    # Permanent patterns
    permanent_patterns = [
        "parse", "invalid", "schema", "validation",
        "not found", "400", "404"
    ]

    if any(p in error_message for p in permanent_patterns):
        return ErrorClassification.PERMANENT

    if error_type in ["XMLParseError", "ValidationError", "SchemaError"]:
        return ErrorClassification.PERMANENT

    # Default to transient
    return ErrorClassification.TRANSIENT
```

## Step 5: Update Settings

Add manifest configuration:

```python
# lovdata_pipeline/config/settings.py

class Settings(BaseSettings):
    # ... existing settings ...

    # Pipeline manifest
    pipeline_manifest_path: Path = Field(
        default=Path("./data/pipeline_manifest.json"),
        description="Path to pipeline manifest file",
    )

    # Manifest behavior
    use_manifest: bool = Field(
        default=True,
        description="Use pipeline manifest for state tracking",
    )

    maintain_legacy_state: bool = Field(
        default=True,
        description="Continue writing to legacy state files during migration",
    )
```

## Step 6: Migration Script

Create a script to migrate existing state to manifest:

```python
# scripts/migrate_to_manifest.py

"""Migrate existing state files to pipeline manifest."""

from pathlib import Path
import json
from lovdata_pipeline.infrastructure.pipeline_manifest import (
    PipelineManifest,
    IndexStatus,
)
from lovdata_pipeline.infrastructure.lovlig_client import LovligClient
from lovdata_pipeline.config.settings import get_settings


def migrate():
    """Migrate existing state to manifest."""
    settings = get_settings()

    # Load manifest
    manifest = PipelineManifest(settings.pipeline_manifest_path)

    # Load lovlig state
    lovlig = LovligClient(
        state_file=settings.state_file,
        extracted_data_dir=settings.extracted_data_dir,
    )

    # Load processed files state
    with open(settings.data_dir / "processed_files.json") as f:
        processed_state = json.load(f)

    # Load embedded files state
    embedded_state_file = settings.data_dir / "embedded_files.json"
    if embedded_state_file.exists():
        with open(embedded_state_file) as f:
            embedded_state = json.load(f)
    else:
        embedded_state = {}

    # Migrate all files
    all_files = lovlig.get_changed_files() + lovlig.get_removed_files()

    for file_meta in all_files:
        doc_id = file_meta.document_id

        # Create document in manifest
        manifest.ensure_document(
            document_id=doc_id,
            dataset_name=file_meta.dataset_name,
            relative_path=file_meta.relative_path,
            file_hash=file_meta.file_hash,
            file_size_bytes=file_meta.file_size_bytes,
        )

        # Check if chunked
        dataset_processed = processed_state.get(file_meta.dataset_name, {})
        if file_meta.relative_path in dataset_processed:
            manifest.complete_stage(
                document_id=doc_id,
                file_hash=file_meta.file_hash,
                stage="chunking",
            )

        # Check if embedded
        dataset_embedded = embedded_state.get(file_meta.dataset_name, {})
        if file_meta.relative_path in dataset_embedded:
            manifest.complete_stage(
                document_id=doc_id,
                file_hash=file_meta.file_hash,
                stage="embedding",
            )
            # Set index status to indexed (assumption)
            manifest.set_index_status(doc_id, IndexStatus.INDEXED)

    # Save manifest
    manifest.save()

    print(f"Migrated {len(manifest.documents)} documents to manifest")


if __name__ == "__main__":
    migrate()
```

## Step 7: Testing

Test the migration:

```bash
# Backup existing state
cp data/processed_files.json data/processed_files.json.backup
cp data/embedded_files.json data/embedded_files.json.backup

# Run migration
uv run python scripts/migrate_to_manifest.py

# Verify manifest
cat data/pipeline_manifest.json | jq '.summary'
```

## Rollout Plan

### Phase 1: Dual-Write (Week 1)

- ✅ Update assets to write to both old and new state
- ✅ Keep all old logic working
- ✅ Monitor for discrepancies

### Phase 2: Read from Manifest (Week 2)

- ✅ Update assets to read from manifest first
- ✅ Fall back to old state if manifest is empty
- ✅ Validate consistency

### Phase 3: Manifest-Only (Week 3)

- ✅ Stop writing to old state files
- ✅ Keep old files for reference
- ✅ Document migration process

### Phase 4: Cleanup (Week 4)

- ✅ Remove old state reading logic
- ✅ Archive old state files
- ✅ Update documentation

## Validation Checklist

After migration, verify:

- [ ] All documents in manifest
- [ ] Stage progression matches old state
- [ ] No documents lost
- [ ] Queries return expected results
- [ ] Assets work with manifest
- [ ] Tests pass
- [ ] No performance regression

## Troubleshooting

### Issue: Manifest file grows too large

**Solution**: Implement per-document manifest sharding:

```python
# Store in manifests/{document_id}.json instead
manifest_file = settings.data_dir / "manifests" / f"{doc_id}.json"
```

### Issue: Concurrent writes corrupt manifest

**Solution**: Add file locking:

```python
import fcntl

with open(manifest_file, "r+") as f:
    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
    # ... read, modify, write ...
    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
```

### Issue: Manifest queries are slow

**Solution**: Add in-memory cache:

```python
class CachedPipelineManifest(PipelineManifest):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._index_cache = {}

    def get_documents_by_index_status(self, status):
        if status not in self._index_cache:
            self._index_cache[status] = super().get_documents_by_index_status(status)
        return self._index_cache[status]
```

## Summary

This integration guide provides:

- ✅ Step-by-step asset updates
- ✅ Backward compatibility strategy
- ✅ Helper functions and decorators
- ✅ Migration script
- ✅ Rollout plan
- ✅ Validation checklist

The key principle is **gradual migration** with **dual-write** to ensure no data loss during transition.
