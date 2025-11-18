# Lovdata Dataset Configuration

## Overview

The pipeline uses the `LOVDATA_DATASET_FILTER` environment variable to control which Lovdata datasets are synced and processed.

## Configuration

Edit `.env` file:

```bash
# Current laws only (default)
LOVDATA_DATASET_FILTER=gjeldende

# All datasets
LOVDATA_DATASET_FILTER=

# Only laws (not regulations)
LOVDATA_DATASET_FILTER=lover

# Only regulations
LOVDATA_DATASET_FILTER=forskrifter

# Repealed/historical laws
LOVDATA_DATASET_FILTER=opphevet
```

## Common Datasets

Based on Lovdata's structure, typical datasets include:

- **gjeldende-lover.tar.bz2** - Current Norwegian laws
- **gjeldende-sentrale-forskrifter.tar.bz2** - Current central regulations
- **opphevet-lover.tar.bz2** - Repealed laws
- **opphevet-sentrale-forskrifter.tar.bz2** - Repealed regulations

## Filter Behavior

The filter uses **partial matching** on dataset filenames:

- `gjeldende` → Matches both `gjeldende-lover.tar.bz2` and `gjeldende-sentrale-forskrifter.tar.bz2`
- `lover` → Matches `gjeldende-lover.tar.bz2` and `opphevet-lover.tar.bz2`
- `""` or `null` → Matches all available datasets

## Quick Commands

```bash
# Sync with current .env settings
make dagster-sync

# Sync all datasets (override filter)
make dagster-sync-all

# Sync specific datasets
LOVDATA_DATASET_FILTER="opphevet" make dagster-sync

# Run full pipeline with specific dataset
LOVDATA_DATASET_FILTER="lover" make dagster-job
```

## Production Configuration

In production, update the `LOVDATA_DATASET_FILTER` environment variable in your deployment configuration:

```yaml
# Example Kubernetes ConfigMap
env:
  - name: LOVDATA_DATASET_FILTER
    value: "gjeldende"
```

Or update `definitions.py` for environment-specific settings:

```python
resources_by_env = {
    "production": {
        "lovlig": LovligResource(
            dataset_filter=EnvVar("LOVDATA_DATASET_FILTER"),
            # ... other config
        ),
    }
}
```

## Checking Downloaded Datasets

```bash
# List downloaded datasets
ls -lh data/raw/

# List extracted files
ls -lh data/extracted/
```

## Notes

- The filter is applied during sync (`lovdata_sync` asset)
- Changing the filter requires re-running sync to download new datasets
- Existing datasets are not automatically removed when filter changes
- To start fresh: `rm -rf data/raw data/extracted data/state.json`
