# Lovdata Pipeline - Dagster Ingestion

A Dagster-based data pipeline for syncing Norwegian legal datasets from Lovdata using the [lovlig](https://github.com/martgra/lovlig) library.

## Features

- **Automated Sync**: Daily scheduled sync of Lovdata datasets
- **Change Detection**: Automatically detects added, modified, and removed files
- **Memory Efficient**: Processes large datasets without loading everything into memory
- **Clean Architecture**: Separation of concerns with domain, infrastructure, and orchestration layers
- **Observable**: Rich metadata and logging in Dagster UI

## Project Structure

```
lovdata_pipeline/
├── assets/                  # Dagster assets (thin orchestration)
│   └── ingestion.py        # Sync and file detection assets
├── config/                  # Configuration
│   └── settings.py         # Pydantic settings with env var support
├── domain/                  # Business logic (pure Python)
│   └── models.py           # Data structures
├── infrastructure/          # External system wrappers
│   └── lovlig_client.py    # Lovlig library client
├── resources/               # Dagster resources
│   └── lovlig.py           # Lovlig resource for assets
└── definitions.py          # Dagster definitions entry point
```

## Quick Start

### 1. Install Dependencies

```bash
make install
# or
uv sync
```

### 2. Configure Environment

Copy the example environment file and adjust as needed:

```bash
cp .env.example .env
```

Edit `.env` to configure your data directories and settings.

### 3. Start Dagster Dev Server

```bash
make dagster-dev
# or
uv run dagster dev -m lovdata_pipeline.definitions
```

Open http://localhost:3000 to access the Dagster UI.

### 4. Run Sync Manually

```bash
make dagster-sync
# or
uv run dagster asset materialize -m lovdata_pipeline.definitions --select lovdata_sync changed_file_paths removed_file_metadata
```

## Assets

### `lovdata_sync`

Syncs datasets from Lovdata using lovlig:

- Downloads changed datasets
- Extracts XML files
- Updates state.json with file hashes
- Returns statistics metadata

**Output**: MaterializeResult with sync statistics

### `changed_file_paths`

Detects files that were added or modified:

- Queries lovlig state
- Returns list of file paths (not contents!)
- Provides metadata about changes

**Output**: List of absolute file paths as strings

### `removed_file_metadata`

Detects files that were removed:

- Queries lovlig state for removed files
- Returns metadata for cleanup
- Includes document IDs

**Output**: List of removal info dictionaries

## Configuration

All settings can be configured via environment variables:

| Variable                           | Default             | Description              |
| ---------------------------------- | ------------------- | ------------------------ |
| `LOVDATA_DATASET_FILTER`           | `gjeldende`         | Dataset filter pattern   |
| `LOVDATA_RAW_DATA_DIR`             | `./data/raw`        | Raw archive directory    |
| `LOVDATA_EXTRACTED_DATA_DIR`       | `./data/extracted`  | Extracted XML directory  |
| `LOVDATA_STATE_FILE`               | `./data/state.json` | State file path          |
| `LOVDATA_MAX_DOWNLOAD_CONCURRENCY` | `4`                 | Max concurrent downloads |

## Scheduling

The pipeline includes a daily schedule that runs at 2 AM Norway time:

```python
daily_sync_schedule = dg.ScheduleDefinition(
    name="daily_lovdata_sync",
    target=[lovdata_sync, changed_file_paths, removed_file_metadata],
    cron_schedule="0 2 * * *",
    execution_timezone="Europe/Oslo",
)
```

Enable the schedule in the Dagster UI to run automatically.

## Development

### Run Tests

```bash
make test
```

### Lint Code

```bash
make lint
```

### Format Code

```bash
make format
```

## Architecture Principles

Following the [architecture guide](docs/architecture_guide.md):

1. **Thin Assets**: Assets delegate to domain logic, don't contain business rules
2. **Fat Domain**: Business logic lives in pure Python modules
3. **Infrastructure Layer**: Wraps external systems (lovlig, filesystem)
4. **Memory Efficiency**: Pass file paths/metadata, not contents

## Next Steps

Downstream assets can:

1. Process XML files one-by-one from `changed_file_paths`
2. Clean up embeddings for documents in `removed_file_metadata`
3. Build indexes, generate embeddings, etc.

Example downstream asset:

```python
@dg.asset
def parsed_chunks(
    context: dg.AssetExecutionContext,
    changed_file_paths: list[str]
) -> dg.MaterializeResult:
    """Parse XML files one-by-one."""
    chunk_count = 0

    for file_path in changed_file_paths:
        # Process single file
        chunks = parse_xml_file(file_path)
        chunk_count += len(chunks)
        # File is garbage collected

    return dg.MaterializeResult(
        metadata={"chunk_count": chunk_count}
    )
```

See [implementation guide](docs/implementation_guide.md) for detailed patterns.

## License

MIT
