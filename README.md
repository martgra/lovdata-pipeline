# lovdata-pipeline

![CI](https://github.com/martgra/lovdata-pipeline/actions/workflows/ci.yaml/badge.svg?branch=main)
![Python](https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white)
[![Copier](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/copier-org/copier/master/img/badge/badge-grayscale-inverted-border-orange.json)](https://github.com/copier-org/copier)

A Dagster-based data pipeline for syncing Norwegian legal datasets from Lovdata.

## 🚀 Quick Start

### Start Dagster UI

```bash
make dagster-dev
```

Open http://localhost:3000 to access the Dagster UI.

### Run Sync

```bash
make dagster-sync
```

## 📚 Documentation

- **[Dagster Pipeline Guide](docs/DAGSTER_README.md)** - Complete pipeline documentation
- **[Quick Reference](docs/QUICK_REFERENCE.md)** - Command cheat sheet
- **[Implementation Summary](docs/IMPLEMENTATION_SUMMARY.md)** - What was built
- **[Architecture Guide](docs/architecture_guide.md)** - Design principles
- **[Implementation Guide](docs/implementation_guide.md)** - Detailed patterns

## ✨ Features

- **Dagster Orchestration** – Clean, observable data pipelines
- **Memory Efficient** – Processes large datasets without loading everything into memory
- **Change Detection** – Automatically detects added, modified, and removed files
- **Daily Scheduling** – Runs at 2 AM Norway time
- **Modern Python** – Requires Python ≥ 3.11
- **Dependency management with uv** – Fast dependency installation and lock file management
- **Quality tools**
  - Ruff formats and lints code
  - Pylint performs deeper static analysis
  - Deptry detects unused, missing and transitive dependencies
  - Vulture finds dead code
- **Secret scanning with detect-secrets** - Prevent secrets getting committed and pushed
- **Git hooks with Prek** – Automated quality checks on every commit and push
- **Automated CI/CD** – GitHub Actions run all Prek hooks on pull requests and pushes to ensure code quality
- **Dev Container** – Devcontainer provides a reproducible environment with Python 3.13, uv and all tools preconfigured

## 🏗️ Architecture

```
lovdata_pipeline/
├── assets/              # Dagster assets (orchestration)
│   └── ingestion.py    # lovdata_sync, changed_file_paths, removed_file_metadata
├── domain/              # Business logic (pure Python)
│   └── models.py       # SyncStatistics, FileMetadata, RemovalInfo
├── infrastructure/      # External system wrappers
│   └── lovlig_client.py # Lovlig library client
├── resources/           # Dagster resources
│   └── lovlig.py       # LovligResource
├── config/              # Configuration
│   └── settings.py     # Pydantic settings
└── definitions.py      # Dagster entry point
```

## 📦 Dependencies

- **dagster** – Data orchestration framework
- **dagster-webserver** – Dagster UI
- **lovdata-processing** – Lovlig library for Lovdata sync
- **pydantic-settings** – Configuration management

## ⚙️ Configuration

Create a `.env` file (see `.env.example`):

```bash
LOVDATA_DATASET_FILTER=gjeldende
LOVDATA_RAW_DATA_DIR=./data/raw
LOVDATA_EXTRACTED_DATA_DIR=./data/extracted
LOVDATA_STATE_FILE=./data/state.json
LOVDATA_MAX_DOWNLOAD_CONCURRENCY=4
```

## Project Layout

```
lovdata_pipeline/         # Your package
tests/                      # Test suite
pyproject.toml              # Dependencies & configuration
uv.lock                     # Locked versions
.pre-commit-config.yaml     # Git hook configuration (used by Prek)
.secrets.baseline           # detect-secrets baseline
Makefile                    # Common tasks (test, lint, format, etc.)
.vscode/                  # VSCode settings
.devcontainer/            # Dev container configuration
.github/workflows/       # CI/CD workflows
```

Python ≥ 3.11 is required locally. The dev container uses Python 3.13.

## Git Hooks (Prek)

[Prek](https://github.com/j178/prek) is a fast Rust‑based replacement for pre‑commit that uses the same configuration format. Install hooks with:

```bash
uvx prek install
```

### Fast Commit Hooks (run on every commit)

- **Ruff** – Lints and formats Python code (auto‑fix enabled)
- **File checks** – Trailing whitespace, end‑of‑file newlines, JSON/YAML/TOML validation
- **Security** – Detect private keys

### Slower Push Hooks (run on `git push`)

- **pytest** – Full test suite
- **Pylint** – Deep static analysis for code design issues
- **Deptry** – Checks for unused, missing, and transitive dependencies
- **Vulture** – Finds dead/unused code
- **detect‑secrets** – Scans for secrets against baseline
- **uv‑lock** – Validates `pyproject.toml` and lock file consistency

This two‑tier approach keeps commits fast while ensuring comprehensive quality checks before pushing.

## CI Pipeline

GitHub Actions run on pull requests and pushes to the main branch. The workflow uses the same Prek configuration, executing all hooks (both commit and push stages) to ensure code quality.

See [`.github/workflows/ci.yaml`](.github/workflows/ci.yaml).

## Devcontainer

For reproducible Docker‑based development, reopen the project in a container (**Dev Containers: Reopen in Container** in VS Code). The container pre‑configures Python 3.13, uv and all tools.

Docs: [VS Code Dev Containers](https://code.visualstudio.com/docs/devcontainers/containers)

## Template Updates

Keep your project current with template improvements:

```bash
uvx copier update
```

Docs: [Copier Updates](https://copier.readthedocs.io/en/stable/updating/)

## License

Distributed under the **MIT License**.
