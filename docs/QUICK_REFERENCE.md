# Lovdata Pipeline Quick Reference

## Start Dagster UI

```bash
make dagster-dev
# or
uv run dagster dev -m lovdata_pipeline.definitions
```

Then open: http://localhost:3000

## Run Sync Manually

```bash
make dagster-sync
# or
uv run dagster asset materialize -m lovdata_pipeline.definitions --select lovdata_sync changed_file_paths removed_file_metadata
```

## Configuration

Create `.env` file (see `.env.example`):

```bash
# Required settings
LOVDATA_DATASET_FILTER=gjeldende
LOVDATA_RAW_DATA_DIR=./data/raw
LOVDATA_EXTRACTED_DATA_DIR=./data/extracted
LOVDATA_STATE_FILE=./data/state.json
LOVDATA_MAX_DOWNLOAD_CONCURRENCY=4
```

## Assets

| Asset                   | Description                 | Output                |
| ----------------------- | --------------------------- | --------------------- |
| `lovdata_sync`          | Syncs datasets from Lovdata | Metadata only         |
| `changed_file_paths`    | Lists added/modified files  | List of file paths    |
| `removed_file_metadata` | Lists removed files         | List of removal dicts |

## Project Structure

```
lovdata_pipeline/
├── assets/              # Dagster assets (thin)
├── domain/              # Business logic (pure Python)
├── infrastructure/      # External system wrappers
├── resources/           # Dagster resources
├── config/              # Configuration
└── definitions.py       # Entry point
```

## Development Commands

```bash
make install      # Install dependencies
make test         # Run tests
make lint         # Check code quality
make format       # Format code
make clean        # Clean cache files
```

## Common Tasks

### View Asset Lineage

1. Open Dagster UI (http://localhost:3000)
2. Click "Assets" in sidebar
3. See dependency graph

### Enable Daily Schedule

1. Open Dagster UI
2. Go to "Overview" > "Schedules"
3. Find "daily_lovdata_sync"
4. Click "Start Schedule"

### Check Run History

1. Open Dagster UI
2. Click "Runs" in sidebar
3. View all past executions

### Debug Failed Run

1. Click on failed run
2. View logs tab
3. See error messages and stack traces

## Memory-Efficient Pattern

Assets return **paths**, not contents:

```python
# Good: Returns paths
changed_file_paths: list[str] = ["./data/file1.xml", "./data/file2.xml"]

# Bad: Returns contents
changed_files: list[str] = ["<xml>...</xml>", "<xml>...</xml>"]  # Memory overflow!
```

Downstream assets process files one-by-one:

```python
@dg.asset
def process_files(changed_file_paths: list[str]):
    for path in changed_file_paths:
        # Load ONE file
        content = parse_xml(path)
        # Process
        # File is garbage collected after loop
```

## Troubleshooting

### "State file not found"

**Cause**: First run, no state.json yet  
**Solution**: Normal - sync will create it

### "Sync failed"

**Cause**: Network issue or lovlig error  
**Solution**: Check logs in Dagster UI, retry

### "No changed files"

**Cause**: Nothing changed since last sync  
**Solution**: Normal - assets succeed with 0 files

### Memory issues

**Cause**: Processing too many files at once  
**Solution**: Process files one-by-one in loop

## Documentation

- **Architecture**: `docs/architecture_guide.md`
- **Implementation**: `docs/implementation_guide.md`
- **Full Guide**: `docs/DAGSTER_README.md`
- **Summary**: `docs/IMPLEMENTATION_SUMMARY.md`

## Dependencies

```bash
# Add to pyproject.toml
dagster
dagster-webserver
lovdata-processing (from git)
pydantic-settings
```

## Schedule Details

**Name**: `daily_lovdata_sync`  
**Cron**: `0 2 * * *` (2 AM daily)  
**Timezone**: Europe/Oslo  
**Targets**: All 3 sync assets

## Next Steps

1. Start Dagster UI: `make dagster-dev`
2. Run initial sync: Click "Materialize all" in UI
3. Enable daily schedule
4. Build downstream processing assets
5. Monitor via UI
