# Quick Start Guide - Testing with Fewer Files

## 🎯 Current Configuration

Your `.env` is now set to:

- **MAX_FILES=10** - Process only 10 files
- **LOVDATA_DATASET_FILTER=lover** - Only laws (not regulations)
- **LANGFUSE_DEBUG=true** - Debug mode enabled

## 🚀 Run the Pipeline via Dagster UI

1. **Start Dagster:**

   ```bash
   dagster dev
   ```

2. **Open UI:**

   - Browser: http://localhost:3000

3. **Materialize Assets:**
   - Click "Assets" in left sidebar
   - Select `lovdata_processing_job` OR individual assets
   - Click "Materialize selected"

## 📊 What to Expect

With 10 files, you should see:

- ~200-500 chunks parsed
- ~1-2 embedding batches
- Fast completion (~30-60 seconds)
- Minimal memory usage

## 🐛 Debug Langfuse Issues

### Option 1: Test Langfuse Connection

```bash
uv run python test_langfuse.py
```

### Option 2: Disable Langfuse (Recommended for Testing)

```bash
# Temporarily disable in terminal
export LANGFUSE_SECRET_KEY=""
export LANGFUSE_PUBLIC_KEY=""
dagster dev
```

Or edit `.env`:

```bash
# Comment out Langfuse keys
# LANGFUSE_SECRET_KEY = "sk-lf-..."
# LANGFUSE_PUBLIC_KEY = "pk-lf-..."
```

### Option 3: Keep Langfuse but Ignore Errors

The 500 errors are non-critical - your pipeline works fine without observability.
Just let it run and ignore the Langfuse warnings.

## 🧪 Testing Workflow

### Quick Test (10 files)

```bash
# In .env: MAX_FILES=10
dagster dev
# Materialize via UI
```

### Medium Test (50 files)

```bash
# In .env: MAX_FILES=50
dagster dev
```

### Full Run

```bash
# In .env: MAX_FILES=0 (or comment out)
dagster dev
```

## 📝 Watch Progress in UI

**During run, check:**

1. **Logs tab** - See batch progress
2. **Assets tab** - See materialization status
3. **Runs tab** - See historical runs

**Look for:**

- "Processing batch X/Y"
- "chunks embedded and written to ChromaDB"
- "Checkpoint cleaned up" (on success)

## 🔍 Verify Results

### Check ChromaDB

```bash
uv run python -c "
from lovdata_pipeline.resources import ChromaDBResource
chromadb = ChromaDBResource()
collection = chromadb.get_or_create_collection()
print(f'Total chunks in ChromaDB: {collection.count()}')
"
```

### Check Checkpoint Files

```bash
ls -lh data/checkpoints/
# Should be empty if job completed successfully
# If job is running, should show small (<50KB) checkpoint file
```

## 🎛️ Environment Variables Quick Reference

**Processing Control:**

- `MAX_FILES=10` - Process 10 files only
- `FILE_BATCH_SIZE=100` - Files per batch
- `EMBEDDING_BATCH_SIZE=2048` - Chunks per OpenAI API call

**Debugging:**

- `LANGFUSE_DEBUG=true` - Enable Langfuse debug mode
- `ENABLE_EMBEDDING_CHECKPOINT=true` - Enable checkpoints

**Dataset Filter:**

- `LOVDATA_DATASET_FILTER=lover` - Laws only
- `LOVDATA_DATASET_FILTER=gjeldende` - All current laws/regs
- `LOVDATA_DATASET_FILTER=forskrifter` - Regulations only

## 🎯 Next Steps

1. Start Dagster: `dagster dev`
2. Open browser: http://localhost:3000
3. Navigate to Assets
4. Click "Materialize all" or select specific assets
5. Watch the logs for progress

**If Langfuse errors persist:**

- They're harmless - just observability
- Disable by commenting out keys in `.env`
- Your pipeline continues working fine

Happy testing! 🚀
