# 🎯 Getting Started Checklist

Use this checklist to get your Lovdata pipeline up and running!

## ☑️ Installation

- [ ] Clone the repository
- [ ] Install dependencies: `make install` or `pip install -e .`
- [ ] Verify installation: `make check-tools`

## ☑️ Configuration

- [ ] Copy environment file: `cp .env.example .env`
- [ ] Add OpenAI API key to `.env`:
  ```
  OPENAI_API_KEY=sk-your-api-key-here
  ```
- [ ] (Optional) Add Langfuse credentials to `.env` for observability:
  ```
  LANGFUSE_PUBLIC_KEY=pk-lf-...
  LANGFUSE_SECRET_KEY=sk-lf-...
  ```
- [ ] Verify data directories exist: `ls -la data/`

## ☑️ Testing

- [ ] Run tests to verify setup: `make test`
- [ ] Check linting: `make lint`
- [ ] Review test output for any failures

## ☑️ First Run

### Option 1: Dagster UI (Recommended)

- [ ] Start Dagster dev server: `make dagster`
- [ ] Open http://localhost:3000 in browser
- [ ] Navigate to "Assets" tab
- [ ] Click "Materialize all" to run pipeline
- [ ] Monitor execution in real-time
- [ ] Check "Runs" tab for detailed logs

### Option 2: CLI

- [ ] Run complete pipeline: `make dagster-job`
- [ ] Wait for completion
- [ ] Check logs for success/errors

## ☑️ Verify Results

After first successful run:

- [ ] Check `data/extracted/` for XML files downloaded from Lovdata
- [ ] Check `data/state.json` exists (lovlig state file)
- [ ] Verify ChromaDB created: `ls -la data/chromadb/`
- [ ] In Dagster UI, verify all assets show "Materialized"
- [ ] Check asset metadata for statistics (chunk counts, embedding counts, etc.)

## ☑️ Query Your Data

Test that embeddings are searchable:

```python
import chromadb

# Connect to ChromaDB
client = chromadb.PersistentClient(path="./data/chromadb")
collection = client.get_collection("lovdata_legal_docs")

# Test query
results = collection.query(
    query_texts=["What are the data processing requirements?"],
    n_results=5
)

print(f"Found {len(results['documents'][0])} results")
for i, doc in enumerate(results['documents'][0]):
    print(f"\n{i+1}. {doc[:200]}...")
```

- [ ] Run query script
- [ ] Verify relevant results returned
- [ ] Check metadata in results

## ☑️ Production Setup (Optional)

For production deployments:

- [ ] Configure production environment in `.env`
- [ ] Set up PostgreSQL for Dagster (optional but recommended)
- [ ] Update `dagster_home/dagster.yaml` for production storage
- [ ] Set up Langfuse project for cost tracking
- [ ] Enable daily schedule in Dagster UI:
  - Navigate to "Schedules"
  - Enable `daily_lovdata_schedule`
- [ ] Configure backup strategy for `data/chromadb/`
- [ ] Set up monitoring/alerting

## ☑️ Docker Deployment (Optional)

If using Docker:

- [ ] Build image: `make docker-build`
- [ ] Update `docker-compose.yml` with your API keys
- [ ] Start containers: `make docker-up`
- [ ] Check logs: `make docker-logs`
- [ ] Access Dagster UI at http://localhost:3000
- [ ] Stop containers when done: `make docker-down`

## 🎉 Success Criteria

You're ready to go when:

- ✅ All tests pass
- ✅ Dagster UI accessible at http://localhost:3000
- ✅ First pipeline run completes successfully
- ✅ XML files visible in `data/extracted/`
- ✅ ChromaDB collection created and queryable
- ✅ Asset metadata shows reasonable counts (chunks, embeddings)
- ✅ No errors in Dagster run logs

## 🆘 Troubleshooting

If you encounter issues:

1. **Check logs**: Dagster UI > Runs > [Your Run] > Logs
2. **Verify API keys**: Test OpenAI key with `curl`
3. **Check disk space**: `df -h`
4. **Review error messages**: Often self-explanatory
5. **Consult documentation**: See [README_PIPELINE.md](README_PIPELINE.md)

## 📚 Next Steps

Once everything works:

1. **Explore assets**: Click on each asset in Dagster UI to see lineage
2. **Review metadata**: Check asset metadata for insights
3. **Enable schedule**: For daily automatic processing
4. **Set up Langfuse**: Track costs and performance
5. **Customize chunking**: Modify parser for your needs
6. **Build RAG application**: Use ChromaDB for semantic search

---

**Having issues?** See [QUICKSTART.md](QUICKSTART.md) or [README_PIPELINE.md](README_PIPELINE.md) for detailed help.

**Everything working?** 🎊 You're ready to process Norwegian legal documents!
