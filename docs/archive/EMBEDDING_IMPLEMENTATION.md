# Embedding Pipeline Implementation

## Overview

The embedding pipeline enriches legal document chunks with OpenAI embeddings, implementing **incremental processing** to only embed changed/added files.

## Architecture

### Pipeline Flow

```
sync → chunk → embed → index
```

The embedding step processes chunks from changed files and enriches them with OpenAI embeddings.

### Key Components

1. **EmbeddedFileClient** (`infrastructure/embedded_file_client.py`)

   - Tracks which files have been embedded
   - Compares file hashes from lovlig state
   - Manages `data/embedded_files.json` state file

2. **ChunkReader** (`infrastructure/chunk_reader.py`)

   - Reads chunks from `legal_chunks.jsonl` by document ID
   - Supports streaming for memory efficiency

3. **EnrichedChunkWriter** (`infrastructure/enriched_writer.py`)

   - Writes enriched chunks with embeddings to JSONL
   - Handles chunk removal for deleted/modified files

4. **embed_chunks()** (`pipeline_steps.py`)
   - Main processing function
   - Three-pass approach: remove deleted → remove modified → embed and write
   - Handles OpenAI API calls with batching and retry logic

## Configuration

### Environment Variables

```bash
# Required
LOVDATA_OPENAI_API_KEY=sk-...

# Optional (with defaults)
LOVDATA_EMBEDDING_MODEL=text-embedding-3-large
LOVDATA_EMBEDDING_BATCH_SIZE=100
LOVDATA_FORCE_REEMBED=false
LOVDATA_ENRICHED_DATA_DIR=./data/enriched
LOVDATA_EMBEDDED_FILES_STATE=./data/embedded_files.json
```

### Settings (settings.py)

```python
enriched_data_dir: Path = Path("./data/enriched")
embedded_files_state: Path = Path("./data/embedded_files.json")
embedding_model: str = "text-embedding-3-large"
embedding_batch_size: int = 100
force_reembed: bool = False
openai_api_key: str = ""
```

## State Management

### Two State Files

1. **`embedded_files.json`** - Tracks embedded files

   ```json
   {
     "gjeldende-lover.tar.bz2": {
       "nl/nl-doc1.xml": {
         "file_hash": "13841ec332b24f39...",
         "embedded_at": "2025-11-18T10:30:00+00:00",
         "chunk_count": 5,
         "model_name": "text-embedding-3-large"
       }
     }
   }
   ```

2. **`data/enriched/embedded_chunks.jsonl`** - Output file
   ```json
   {"chunk_id": "...", "content": "...", "embedding": [0.1, 0.2, ...], "embedding_model": "text-embedding-3-large"}
   ```

## Incremental Logic

### File Selection

Files need embedding when:

```python
if force_reembed:
    embed all changed files
elif file_hash != embedded_hash:
    embed (hash changed)
elif file not in embedded_state:
    embed (never embedded)
else:
    skip (already embedded)
```

### Processing Flow

**Pass 1A: Remove embeddings for deleted files**

```python
for removal in removed_file_metadata:
    writer.remove_chunks_for_document(removal["document_id"])
```

**Pass 1B: Remove embeddings for modified files**

```python
for file_meta in files_to_embed:
    writer.remove_chunks_for_document(file_meta.document_id)
```

**Pass 2: Embed and write**

```python
for file_meta in files_to_embed:
    chunks = chunk_reader.read_chunks_for_document(doc_id)

    # Embed in batches
    for batch in batches(chunk_texts, batch_size):
        embeddings = embedding.embed_batch(batch)

    # Write enriched chunks
    for chunk, emb in zip(chunks, embeddings):
        writer.write_chunk({**chunk, "embedding": emb})

    # Mark as embedded
    embedding.mark_file_embedded(...)
```

## Usage

### Basic Run

```bash
# Set API key
export LOVDATA_OPENAI_API_KEY=sk-...

# Run embedding step
make embed
# or: uv run python -m lovdata_pipeline embed
```

### Force Re-embedding

```bash
# Re-embed all files (e.g., after model upgrade)
uv run python -m lovdata_pipeline embed --force-reembed
```

### Run Full Pipeline

```bash
# Sync → Chunk → Embed → Index
make full
# or: uv run python -m lovdata_pipeline full
```

## Performance

### Incremental Benefits

- **Initial run**: Embeds all files
- **Daily run**: Only embeds changed files
- **Cost savings**: 99%+ on unchanged datasets

### Example

```
Dataset: 10,000 legal documents
Initial run: 10,000 files → ~20,000 chunks → $X
Daily update: 50 changed files → ~100 chunks → $0.005X (99.5% saved!)
```

### Batch Processing

- Default batch size: 100 chunks per API call
- Adjustable via `LOVDATA_EMBEDDING_BATCH_SIZE`
- OpenAI API limit: 2,048 inputs per request

## Error Handling

### Automatic Recovery

- Failed files logged but don't stop pipeline
- Files not marked as embedded will be retried on next run
- Partial embeddings preserved (append-only writes)

### Manual Recovery

```bash
# Check embedded state
cat data/embedded_files.json | jq '.["gjeldende-lover.tar.bz2"] | keys'

# Force re-embed all files
uv run python -m lovdata_pipeline embed --force-reembed
```

## Testing

### Integration Tests

```bash
# Run embedding tests
uv run pytest tests/integration/test_embedding_incremental.py -v

# Run all integration tests
uv run pytest tests/integration/ -v
```

### Test Coverage

1. **Incremental updates** - Add, modify, remove files
2. **Force re-embed** - Bypass state checking
3. **State management** - Hash comparison logic
4. **Chunk removal** - Deleted file cleanup

## Monitoring

### Pipeline Statistics

The embedding step provides detailed statistics:

- `files_embedded` - Number of files processed
- `chunks_embedded` - Total embeddings generated
- `files_deleted` - Removed files cleaned up
- `chunks_removed_for_deleted` - Embeddings removed
- `output_size_mb` - Output file size
- `model_name` - Embedding model used
- `success_rate` - Percentage of successful embeds

### Logs

```
✓ Embedded 50 files successfully
✓ Generated 125 embeddings
✓ Output size: 15.32 MB
⚠ 2 files failed to embed
```

## Model Information

### text-embedding-3-large

- **Dimensions**: 3,072 (default) or custom via `dimensions` parameter
- **Max input**: 8,191 tokens
- **Performance**: MTEB score of 64.6
- **Cost**: $0.00013 per 1K tokens (as of Nov 2024)

### Alternative Models

Update `LOVDATA_EMBEDDING_MODEL`:

- `text-embedding-3-small` - 1,536 dimensions, cheaper
- `text-embedding-ada-002` - Legacy, 1,536 dimensions

## Troubleshooting

### Files not being embedded

- Check `embedded_files.json` for existing entries
- Verify file hash in `state.json` matches
- Use `LOVDATA_FORCE_REEMBED=true` to bypass checks

### API errors

- Verify `LOVDATA_OPENAI_API_KEY` is set correctly
- Check rate limits (3,000 RPM for Tier 1)
- Reduce `LOVDATA_EMBEDDING_BATCH_SIZE` if hitting limits

### Old embeddings not removed

- Ensure Pass 1A and 1B run before Pass 2
- Check document_id extraction from file paths
- Verify writer isn't opened during removal phase

## Future Enhancements

- Parallel embedding (multiple files at once)
- Caching by content hash (deduplicate identical chunks)
- Embedding quality metrics
- Vector database integration
- Semantic search endpoints
