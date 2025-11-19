# Dagster Implementation Guide for Lovlig Data Ingestion

## Table of Contents

1. [Dagster Fundamentals](#dagster-fundamentals)
2. [Creating the Lovlig Resource](#creating-the-lovlig-resource)
3. [Asset 1: Lovdata Sync](#asset-1-lovdata-sync)
4. [Asset 2: Changed Files Detection](#asset-2-changed-files-detection)
5. [Asset 3: Removed Files Detection](#asset-3-removed-files-detection)
6. [The Critical Pattern: Streaming Without Memory Overload](#the-critical-pattern-streaming-without-memory-overload)
7. [Schedules and Sensors](#schedules-and-sensors)
8. [Error Handling and Monitoring](#error-handling-and-monitoring)
9. [Complete Example](#complete-example)

---

## Dagster Fundamentals

### What is an Asset?

An **asset** in Dagster represents a data object you care about (a table, file, ML model, etc.). Think of assets as the _nouns_ of your data pipeline, not the _verbs_.

**Key concept**: Assets know what they produce and what they depend on. Dependencies are declared through function arguments.

```python
import dagster as dg

@dg.asset
def raw_data():
    """This asset produces raw data"""
    return [1, 2, 3]

@dg.asset
def processed_data(raw_data):  # Depends on raw_data (note the argument name)
    """This asset depends on raw_data"""
    return [x * 2 for x in raw_data]
```

### What is a Resource?

A **resource** is a reusable object that provides access to external systems (databases, APIs, file systems). Resources are shared across assets and configured in one place.

```python
class MyDatabaseResource(dg.ConfigurableResource):
    connection_string: str

    def query(self, sql: str):
        # Connect and query
        pass

@dg.asset
def my_asset(database: MyDatabaseResource):
    return database.query("SELECT * FROM table")
```

### The Context Object

The `context` parameter gives you access to logging, configuration, and run information:

```python
@dg.asset
def my_asset(context: dg.AssetExecutionContext):
    context.log.info("Starting asset")
    context.log.warning("Something to watch")
    context.log.error("Something failed")
```

### MaterializeResult vs Returning Data

**Critical distinction for your use case**:

- **Return data directly**: When data fits in memory and should be passed to downstream assets
- **Return MaterializeResult**: When data is too large for memory; only pass _metadata_ downstream

```python
# Small data - return directly
@dg.asset
def small_dataset():
    return {"count": 100, "status": "ok"}

# Large data - return only metadata
@dg.asset
def large_dataset():
    # Write data to disk/database here
    with open("/path/to/large_file.csv", "w") as f:
        # ... write large data
        pass

    return dg.MaterializeResult(
        metadata={
            "file_path": "/path/to/large_file.csv",
            "row_count": 1_000_000,
            "file_size_mb": dg.MetadataValue.float(250.5)
        }
    )
```

---

## Creating the Lovlig Resource

Lovlig is a library written by me and can be added as a dependency to pyproject.toml
https://github.com/martgra/lovlig

The resource wraps lovlig's functionality and makes it available to Dagster assets.

```python
from dagster import ConfigurableResource, EnvVar
from pathlib import Path
from typing import List, Dict
import json

# Import lovlig
from lovdata_processing import (
    sync_datasets,
    Settings as LovligSettings,
    StateManager,
    FileQueryService
)


class LovligResource(ConfigurableResource):
    """
    Dagster resource for interacting with lovlig.

    This resource provides methods to:
    - Sync datasets from Lovdata
    - Query changed files from state
    - Get file metadata without loading file contents
    """

    # Configuration parameters
    dataset_filter: str = "gjeldende"
    raw_data_dir: str = "./data/raw"
    extracted_data_dir: str = "./data/extracted"
    state_file: str = "./data/state.json"
    max_download_concurrency: int = 4

    def get_lovlig_settings(self) -> LovligSettings:
        """Create lovlig Settings object from Dagster config."""
        return LovligSettings(
            dataset_filter=self.dataset_filter,
            raw_data_dir=Path(self.raw_data_dir),
            extracted_data_dir=Path(self.extracted_data_dir),
            state_file=Path(self.state_file),
            max_download_concurrency=self.max_download_concurrency
        )

    def sync_datasets(self, force_download: bool = False) -> None:
        """
        Execute lovlig's dataset sync.
        Downloads, extracts, and updates state.json.
        """
        settings = self.get_lovlig_settings()
        sync_datasets(config=settings, force_download=force_download)

    def get_changed_files(self, status: str) -> List[Dict]:
        """
        Query lovlig's state for files with given status.

        Args:
            status: "added", "modified", or "removed"

        Returns:
            List of file metadata dicts (NOT file contents!)
        """
        settings = self.get_lovlig_settings()
        query_service = FileQueryService()

        with StateManager(settings.state_file) as state:
            return query_service.get_files_by_filter(
                state=state.data,
                status=status
            )

    def get_file_path(self, file_metadata: Dict) -> Path:
        """
        Convert file metadata to absolute path.

        Args:
            file_metadata: Dict with 'path' key from lovlig state

        Returns:
            Absolute path to XML file
        """
        settings = self.get_lovlig_settings()
        return settings.extracted_data_dir / file_metadata["path"]

    def get_statistics(self) -> Dict[str, int]:
        """Get statistics about changed files."""
        return {
            "added": len(self.get_changed_files("added")),
            "modified": len(self.get_changed_files("modified")),
            "removed": len(self.get_changed_files("removed"))
        }
```

**Why this design?**

- lovlig does the heavy lifting (download, extract, hash)
- Resource provides clean interface for Dagster
- No data loaded into memory - only metadata queries

---

## Asset 1: Lovdata Sync

This asset orchestrates lovlig to sync datasets. It returns metadata about what changed, NOT the actual files.

```python
import dagster as dg
from typing import Dict


@dg.asset(
    group_name="ingestion",
    compute_kind="lovlig"
)
def lovdata_sync(
    context: dg.AssetExecutionContext,
    lovlig: LovligResource
) -> dg.MaterializeResult:
    """
    Sync Lovdata datasets using lovlig.

    This asset:
    1. Calls lovlig to download/extract datasets
    2. Updates state.json with file hashes
    3. Returns statistics about changes

    Returns MaterializeResult with metadata (not actual files).
    """
    context.log.info("Starting Lovdata dataset sync")

    try:
        # Execute lovlig sync (this downloads, extracts, updates state)
        lovlig.sync_datasets(force_download=False)

        # Get statistics about what changed
        stats = lovlig.get_statistics()

        context.log.info(
            f"Sync complete: {stats['added']} added, "
            f"{stats['modified']} modified, {stats['removed']} removed"
        )

        # Return metadata (not files!)
        return dg.MaterializeResult(
            metadata={
                "files_added": dg.MetadataValue.int(stats["added"]),
                "files_modified": dg.MetadataValue.int(stats["modified"]),
                "files_removed": dg.MetadataValue.int(stats["removed"]),
                "total_changed": dg.MetadataValue.int(
                    stats["added"] + stats["modified"]
                ),
                "sync_timestamp": dg.MetadataValue.timestamp(
                    context.partition_time_window.start
                    if context.has_partition_key
                    else None
                )
            }
        )

    except Exception as e:
        context.log.error(f"Sync failed: {e}")
        raise
```

**Key points**:

- `lovlig.sync_datasets()` does all the work
- We only return **metadata** about what happened
- No XML files loaded into memory
- Metadata appears in Dagster UI for monitoring

---

## Asset 2: Changed Files Detection

This asset queries lovlig's state and returns a **list of file paths**, not file contents.

```python
from typing import List, Dict


@dg.asset(
    group_name="ingestion",
    compute_kind="lovlig",
    deps=[lovdata_sync]  # Wait for sync to complete
)
def changed_file_paths(
    context: dg.AssetExecutionContext,
    lovlig: LovligResource
) -> List[str]:
    """
    Get list of XML file paths that need processing.

    CRITICAL: This asset returns PATHS, not file contents!
    Downstream assets will load files one-by-one.

    Returns:
        List of absolute file paths as strings
    """
    context.log.info("Querying lovlig state for changed files")

    # Get file metadata from lovlig (not contents!)
    added_files = lovlig.get_changed_files("added")
    modified_files = lovlig.get_changed_files("modified")

    all_changed = added_files + modified_files

    # Convert to absolute paths
    file_paths = []
    for file_meta in all_changed:
        file_path = lovlig.get_file_path(file_meta)

        # Verify file exists
        if file_path.exists():
            file_paths.append(str(file_path))
        else:
            context.log.warning(f"File not found: {file_path}")

    context.log.info(f"Found {len(file_paths)} files to process")

    # Log metadata to Dagster UI
    context.add_output_metadata({
        "file_count": len(file_paths),
        "added_count": len(added_files),
        "modified_count": len(modified_files),
        "sample_files": file_paths[:5]  # Show first 5
    })

    # Return list of paths (strings fit in memory!)
    return file_paths
```

**Why this works**:

- Returns a **list of strings** (file paths)
- Even 10,000 paths is only ~1MB of memory
- Downstream assets iterate through paths and load files one-at-a-time

---

## Asset 3: Removed Files Detection

Similar pattern - return metadata about removed files, not file contents.

```python
@dg.asset(
    group_name="ingestion",
    compute_kind="lovlig",
    deps=[lovdata_sync]
)
def removed_file_metadata(
    context: dg.AssetExecutionContext,
    lovlig: LovligResource
) -> List[Dict]:
    """
    Get metadata about files removed from Lovdata.

    Returns list of dicts with document IDs and metadata
    (NOT file contents - files are already deleted!)
    """
    context.log.info("Querying lovlig state for removed files")

    removed_files = lovlig.get_changed_files("removed")

    # Extract document IDs for downstream deletion
    removal_info = []
    for file_meta in removed_files:
        # Extract document ID from path
        # e.g., "gjeldende-lover/nl/LOV-1999-07-02-63.xml" -> "LOV-1999-07-02-63"
        file_path = Path(file_meta["path"])
        doc_id = file_path.stem

        removal_info.append({
            "document_id": doc_id,
            "file_path": file_meta["path"],
            "dataset": file_meta.get("dataset", "unknown"),
            "last_hash": file_meta.get("hash", "")
        })

    context.log.info(f"Found {len(removal_info)} removed files")

    context.add_output_metadata({
        "removed_count": len(removal_info),
        "document_ids": [r["document_id"] for r in removal_info[:10]]
    })

    return removal_info
```

---

## The Critical Pattern: Streaming Without Memory Overload

### The Problem

You have 3,000+ XML files. If you load them all into memory, you'll crash. But assets need to depend on each other.

### The Solution: Pass Metadata, Not Data

**Pattern**: Upstream assets return **references** (paths, IDs). Downstream assets **iterate** through references, processing one item at a time.

### Example: Processing XML Files One-by-One

```python
from pathlib import Path
from typing import List, Dict
import lxml.etree as ET


@dg.asset(
    group_name="processing",
    compute_kind="xml_parsing"
)
def parsed_chunk_metadata(
    context: dg.AssetExecutionContext,
    changed_file_paths: List[str]  # Just paths, not contents!
) -> List[Dict]:
    """
    Parse XML files and extract chunk metadata.

    MEMORY-EFFICIENT: Processes files one-at-a-time.
    """

    if not changed_file_paths:
        context.log.info("No files to process")
        return []

    chunk_metadata_list = []

    # Process files ONE AT A TIME
    for file_path in changed_file_paths:
        context.log.info(f"Processing {Path(file_path).name}")

        try:
            # Load and parse SINGLE file
            tree = ET.parse(file_path)
            root = tree.getroot()

            # Extract chunks from this file
            chunks_from_file = extract_chunks(root, file_path)

            # Store metadata (not full text!)
            for chunk in chunks_from_file:
                chunk_metadata_list.append({
                    "chunk_id": chunk.chunk_id,
                    "document_id": chunk.metadata["document_id"],
                    "file_path": file_path,
                    "token_count": chunk.metadata.get("token_count", 0),
                    "section_title": chunk.metadata.get("section_title", "")
                })

            # CRITICAL: Don't keep file in memory!
            # Python garbage collection will clean up 'tree' and 'root'
            # after this iteration

        except Exception as e:
            context.log.error(f"Failed to parse {file_path}: {e}")
            # Continue processing other files
            continue

    context.log.info(
        f"Extracted {len(chunk_metadata_list)} chunks from "
        f"{len(changed_file_paths)} files"
    )

    context.add_output_metadata({
        "total_chunks": len(chunk_metadata_list),
        "files_processed": len(changed_file_paths),
        "avg_chunks_per_file": len(chunk_metadata_list) / len(changed_file_paths)
    })

    # Return metadata list (fits in memory!)
    return chunk_metadata_list


def extract_chunks(root, file_path):
    """
    Helper function to extract chunks from XML.
    This is just a placeholder - use your actual logic.
    """
    # Your LovdataXMLParser logic here
    pass
```

### The Memory Profile

```
Maximum memory usage =
    Size of largest single XML file
    + Size of parsed chunks from that file
    + ~100MB overhead

NOT = Sum of all XML files
```

### Alternative: Write to Intermediate Storage

If even single-file parsing uses too much memory, write results incrementally:

```python
@dg.asset
def parsed_chunks_to_jsonl(
    context: dg.AssetExecutionContext,
    changed_file_paths: List[str]
) -> dg.MaterializeResult:
    """
    Parse files and stream results to JSONL file.
    Downstream assets can read line-by-line.
    """
    output_file = Path("/tmp/chunks.jsonl")
    chunk_count = 0

    with open(output_file, "w") as f:
        for file_path in changed_file_paths:
            chunks = parse_xml_file(file_path)

            for chunk in chunks:
                # Write one chunk per line
                f.write(json.dumps(chunk.to_dict()) + "\n")
                chunk_count += 1

                # Chunk object is garbage collected

    return dg.MaterializeResult(
        metadata={
            "output_file": str(output_file),
            "chunk_count": chunk_count,
            "file_size_mb": output_file.stat().st_size / 1_000_000
        }
    )


@dg.asset
def process_chunks_streaming(
    parsed_chunks_to_jsonl: dg.MaterializeResult
) -> dg.MaterializeResult:
    """Read chunks one-by-one from JSONL file."""

    # Extract file path from upstream metadata
    chunk_file = Path(parsed_chunks_to_jsonl.metadata["output_file"])

    processed_count = 0
    with open(chunk_file, "r") as f:
        for line in f:
            chunk_dict = json.loads(line)
            # Process single chunk
            process_single_chunk(chunk_dict)
            processed_count += 1

    return dg.MaterializeResult(
        metadata={"processed_count": processed_count}
    )
```

---

## Schedules and Sensors

### Schedule: Run Daily

```python
from dagster import ScheduleDefinition


# Define a schedule to run daily at 2 AM Norway time
daily_lovdata_sync_schedule = ScheduleDefinition(
    name="daily_lovdata_sync",
    target=[lovdata_sync, changed_file_paths, removed_file_metadata],
    cron_schedule="0 2 * * *",  # 2 AM daily
    execution_timezone="Europe/Oslo"
)
```

### Sensor: Detect State File Changes

If lovlig runs outside Dagster, detect changes with a sensor:

```python
from dagster import sensor, RunRequest, SkipReason, SensorEvaluationContext
from pathlib import Path
import json


@sensor(
    name="lovlig_state_change_sensor",
    minimum_interval_seconds=300,  # Check every 5 minutes
    target=[changed_file_paths, removed_file_metadata]
)
def detect_lovlig_state_changes(
    context: SensorEvaluationContext,
    lovlig: LovligResource
) -> RunRequest | SkipReason:
    """
    Sensor that detects when lovlig's state.json is updated.
    Triggers processing of changed files.
    """
    state_file = Path(lovlig.state_file)

    if not state_file.exists():
        return SkipReason("State file does not exist")

    # Get current state file modification time
    current_mtime = state_file.stat().st_mtime

    # Get last seen modification time from cursor
    last_mtime = context.cursor

    if last_mtime is None:
        # First run - establish baseline
        context.update_cursor(str(current_mtime))
        return SkipReason("Establishing baseline")

    if current_mtime > float(last_mtime):
        # State file was updated!
        context.update_cursor(str(current_mtime))

        # Check if there are actually changed files
        stats = lovlig.get_statistics()
        total_changed = stats["added"] + stats["modified"]

        if total_changed > 0:
            return RunRequest(
                run_key=f"state_change_{current_mtime}",
                run_config={}
            )
        else:
            return SkipReason("State file updated but no changed files")
    else:
        return SkipReason("No state file changes detected")
```

**How sensors work**:

- Run on a loop (every `minimum_interval_seconds`)
- Check for external events
- Return `RunRequest` to trigger downstream assets
- Return `SkipReason` to skip with explanation
- Use `cursor` to track state between runs

---

## Error Handling and Monitoring

### Retry Policy

Add retries for transient failures:

```python
from dagster import RetryPolicy, Backoff


@dg.asset(
    retry_policy=RetryPolicy(
        max_retries=3,
        delay=5,  # seconds
        backoff=Backoff.EXPONENTIAL
    )
)
def lovdata_sync_with_retry(
    context: dg.AssetExecutionContext,
    lovlig: LovligResource
) -> dg.MaterializeResult:
    """Sync with automatic retries on failure."""
    # Implementation same as before
    pass
```

### Logging Levels

```python
@dg.asset
def my_asset(context: dg.AssetExecutionContext):
    context.log.debug("Detailed info for debugging")
    context.log.info("Normal operation")
    context.log.warning("Something to watch")
    context.log.error("Something failed")
```

### Partial Success Handling

```python
@dg.asset
def process_files_with_error_handling(
    context: dg.AssetExecutionContext,
    changed_file_paths: List[str]
) -> dg.MaterializeResult:
    """Process files and track failures."""

    successful = 0
    failed = []

    for file_path in changed_file_paths:
        try:
            process_file(file_path)
            successful += 1
        except Exception as e:
            context.log.error(f"Failed {file_path}: {e}")
            failed.append(file_path)
            # Continue processing other files

    # Return result with failure information
    result = dg.MaterializeResult(
        metadata={
            "successful": successful,
            "failed": len(failed),
            "failed_files": failed[:10],  # Sample
            "success_rate": successful / len(changed_file_paths) * 100
        }
    )

    # If too many failures, raise exception to fail the asset
    if len(failed) > len(changed_file_paths) * 0.5:
        raise Exception(f"More than 50% of files failed: {len(failed)}")

    return result
```

---

## Complete Example

Here's how everything fits together:

```python
# resources.py
from dagster import ConfigurableResource, EnvVar
from pathlib import Path
from lovdata_processing import sync_datasets, Settings, StateManager, FileQueryService


class LovligResource(ConfigurableResource):
    dataset_filter: str = "gjeldende"
    raw_data_dir: str = "./data/raw"
    extracted_data_dir: str = "./data/extracted"
    state_file: str = "./data/state.json"
    max_download_concurrency: int = 4

    def get_lovlig_settings(self):
        return Settings(
            dataset_filter=self.dataset_filter,
            raw_data_dir=Path(self.raw_data_dir),
            extracted_data_dir=Path(self.extracted_data_dir),
            state_file=Path(self.state_file),
            max_download_concurrency=self.max_download_concurrency
        )

    def sync_datasets(self, force_download: bool = False):
        settings = self.get_lovlig_settings()
        sync_datasets(config=settings, force_download=force_download)

    def get_changed_files(self, status: str):
        settings = self.get_lovlig_settings()
        query_service = FileQueryService()
        with StateManager(settings.state_file) as state:
            return query_service.get_files_by_filter(state=state.data, status=status)

    def get_file_path(self, file_metadata):
        settings = self.get_lovlig_settings()
        return settings.extracted_data_dir / file_metadata["path"]


# assets.py
import dagster as dg
from typing import List, Dict
from pathlib import Path


@dg.asset(group_name="ingestion", compute_kind="lovlig")
def lovdata_sync(
    context: dg.AssetExecutionContext,
    lovlig: LovligResource
) -> dg.MaterializeResult:
    """Sync Lovdata datasets using lovlig."""
    context.log.info("Starting sync")

    lovlig.sync_datasets(force_download=False)

    added = lovlig.get_changed_files("added")
    modified = lovlig.get_changed_files("modified")
    removed = lovlig.get_changed_files("removed")

    return dg.MaterializeResult(
        metadata={
            "files_added": len(added),
            "files_modified": len(modified),
            "files_removed": len(removed)
        }
    )


@dg.asset(group_name="ingestion", deps=[lovdata_sync])
def changed_file_paths(
    context: dg.AssetExecutionContext,
    lovlig: LovligResource
) -> List[str]:
    """Get file paths that need processing."""
    added = lovlig.get_changed_files("added")
    modified = lovlig.get_changed_files("modified")

    paths = []
    for file_meta in added + modified:
        path = lovlig.get_file_path(file_meta)
        if path.exists():
            paths.append(str(path))

    context.log.info(f"Found {len(paths)} files to process")
    return paths


@dg.asset(group_name="ingestion", deps=[lovdata_sync])
def removed_file_metadata(
    context: dg.AssetExecutionContext,
    lovlig: LovligResource
) -> List[Dict]:
    """Get metadata about removed files."""
    removed = lovlig.get_changed_files("removed")

    removal_info = []
    for file_meta in removed:
        doc_id = Path(file_meta["path"]).stem
        removal_info.append({
            "document_id": doc_id,
            "file_path": file_meta["path"]
        })

    return removal_info


# definitions.py
from dagster import Definitions, EnvVar, ScheduleDefinition


daily_schedule = ScheduleDefinition(
    name="daily_lovdata_sync",
    target=[lovdata_sync, changed_file_paths, removed_file_metadata],
    cron_schedule="0 2 * * *",
    execution_timezone="Europe/Oslo"
)


defs = Definitions(
    assets=[
        lovdata_sync,
        changed_file_paths,
        removed_file_metadata
    ],
    resources={
        "lovlig": LovligResource(
            dataset_filter=EnvVar("LOVDATA_DATASET_FILTER"),
            raw_data_dir=EnvVar("LOVDATA_RAW_DIR"),
            extracted_data_dir=EnvVar("LOVDATA_EXTRACTED_DIR"),
            state_file=EnvVar("LOVDATA_STATE_FILE"),
            max_download_concurrency=4
        )
    },
    schedules=[daily_schedule]
)
```

---

## Key Takeaways

### ✅ Do This:

- Return file **paths** or **metadata** from assets, not file contents
- Process large datasets one-item-at-a-time in downstream assets
- Use MaterializeResult to attach metadata visible in UI
- Let lovlig handle the heavy lifting (download, extract, hash)
- Use resources for shared configuration and external system access

### ❌ Don't Do This:

- Don't return lists of parsed XML documents from assets
- Don't load all files into memory at once
- Don't pass large dataframes between assets
- Don't duplicate lovlig's logic in Dagster code

### 🎯 The Pattern:

```
lovlig (sync) → state.json updated
     ↓
Asset 1: Query state.json → Return list of file paths (strings)
     ↓
Asset 2: Iterate paths → Process each file → Return metadata
     ↓
Asset 3: Use metadata → Continue pipeline
```
