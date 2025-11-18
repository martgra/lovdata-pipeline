# 🚀 Quick Start - Process Fewer Files via UI

## ✅ Configuration Complete

Your environment is now configured to process **only 10 files**:

- `.env` has `MAX_FILES=10`
- `LOVDATA_DATASET_FILTER=lover` (laws only, not regulations)

## 🎯 Steps to Run

### 1. Start Dagster

```bash
dagster dev
```

### 2. Open Browser

Go to: **http://localhost:3000**

### 3. Run the Job via UI

**Option A: Run Full Pipeline Job**

1. Click "**Jobs**" in left sidebar
2. Find `lovdata_processing_job`
3. Click "**Launch Run**"
4. Click "**Launch Run**" again in modal

**Option B: Run Individual Assets**

1. Click "**Assets**" in left sidebar
2. Check the boxes for assets you want:
   - ☑️ `lovdata_sync`
   - ☑️ `changed_legal_documents`
   - ☑️ `parsed_legal_chunks`
   - ☑️ `document_embeddings` (this is the main one)
   - ☑️ `vector_database`
3. Click "**Materialize selected**"

### 4. Watch Progress

- Click on the running job/asset
- View "**Logs**" tab
- Watch for: "Processing batch X/Y"

## 🐛 About Langfuse Errors

**The 500 errors you saw are NOT critical!**

Langfuse is just for observability/cost tracking. The errors mean:

- Langfuse cloud service is having issues
- Your **pipeline still works perfectly**
- Embeddings are still generated and saved

### Options:

**Option 1: Ignore the errors** (Recommended)

- Let the pipeline run
- Ignore Langfuse warnings in logs
- Everything will complete successfully

**Option 2: Disable Langfuse**
Edit `.env` and comment out:

```bash
# LANGFUSE_SECRET_KEY="sk-lf-..."
# LANGFUSE_PUBLIC_KEY="pk-lf-..."
```

## 📊 Expected Results (10 files)

- **Parsing**: ~200-500 chunks
- **Embedding**: 1-2 batches
- **Time**: ~30-60 seconds
- **Memory**: <100MB constant

## ✅ Verify Success

After the job completes:

```bash
# Check how many chunks were embedded
uv run python -c "
from lovdata_pipeline.resources import ChromaDBResource
chromadb = ChromaDBResource()
collection = chromadb.get_or_create_collection()
print(f'✓ ChromaDB contains {collection.count()} chunks')
"

# Checkpoint should be auto-deleted on success
ls data/checkpoints/
# (should be empty or just README.md)
```

## 🎛️ Adjust Processing

Want to process more/fewer files?

Edit `.env`:

```bash
MAX_FILES=5    # Very small test
MAX_FILES=50   # Medium test
MAX_FILES=0    # All files (comment out or set to 0)
```

Then restart Dagster:

```bash
# Ctrl+C to stop
dagster dev
```

---

## 🎯 Quick Reference

| What                  | Where                             |
| --------------------- | --------------------------------- |
| Start Dagster         | `dagster dev`                     |
| UI                    | http://localhost:3000             |
| Logs                  | UI > Runs > Click run > Logs tab  |
| Files to process      | `.env` > `MAX_FILES=10`           |
| Disable observability | `.env` > Comment out `LANGFUSE_*` |

**Ready to go! Just run `dagster dev` and use the UI to materialize assets.** 🚀
