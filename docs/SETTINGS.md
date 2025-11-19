# Using PipelineSettings

## Quick Start

The pipeline now uses `pydantic-settings` for type-safe configuration management.

### Basic Usage

```bash
# Set environment variable
export OPENAI_API_KEY=sk-your-key-here

# Run with defaults
lovdata-pipeline process

# Override specific settings
lovdata-pipeline process --dataset gjeldende-lover --force
```

### Using .env File

Create a `.env` file in the project root:

```env
OPENAI_API_KEY=sk-your-key-here
EMBEDDING_MODEL=text-embedding-3-large
CHUNK_MAX_TOKENS=6800
DATA_DIR=./data
CHROMA_PATH=./data/chroma
```

### Programmatic Usage

```python
from lovdata_pipeline.settings import PipelineSettings

# Load from environment
settings = PipelineSettings()

# Override specific values
settings = PipelineSettings(
    dataset_filter="gjeldende-lover",
    force=True,
    chunk_max_tokens=5000
)

# Use in pipeline
from lovdata_pipeline.pipeline import run_pipeline

config = settings.to_dict()
result = run_pipeline(config)
```

### Configuration Options

| Setting            | Env Var            | Type | Default                  | Description                            |
| ------------------ | ------------------ | ---- | ------------------------ | -------------------------------------- |
| `openai_api_key`   | `OPENAI_API_KEY`   | str  | _required_               | OpenAI API key (must start with 'sk-') |
| `embedding_model`  | `EMBEDDING_MODEL`  | str  | `text-embedding-3-large` | OpenAI embedding model                 |
| `data_dir`         | `DATA_DIR`         | Path | `./data`                 | Root data directory                    |
| `chroma_path`      | `CHROMA_PATH`      | Path | `./data/chroma`          | ChromaDB persistence path              |
| `chunk_max_tokens` | `CHUNK_MAX_TOKENS` | int  | `6800`                   | Maximum tokens per chunk (100-10000)   |
| `dataset_filter`   | `DATASET_FILTER`   | str  | `gjeldende`              | Dataset filter pattern                 |
| `force`            | `FORCE`            | bool | `false`                  | Force reprocess all files              |

### Dataset Filter Options

- `gjeldende` - Both laws and regulations (full dataset)
- `gjeldende-lover` - Only laws (~1/5 size, recommended for testing)
- `gjeldende-sentrale-forskrifter` - Only central regulations
- `*` - All available datasets

### Validation

Settings are validated on load:

```python
# ❌ Invalid API key format
PipelineSettings(openai_api_key="invalid")
# ValidationError: OpenAI API key must start with 'sk-'

# ❌ Chunk size out of bounds
PipelineSettings(chunk_max_tokens=50)
# ValidationError: Input should be greater than or equal to 100

# ✅ Valid configuration
settings = PipelineSettings(
    openai_api_key="sk-test123456789012345678",
    chunk_max_tokens=5000
)
```

### Environment Variable Names

Environment variables are case-insensitive:

```bash
# All of these work
export OPENAI_API_KEY=sk-...
export openai_api_key=sk-...
export OpenAI_API_Key=sk-...
```

### CLI Override Priority

Settings are loaded in this priority order (highest to lowest):

1. CLI arguments (`--dataset gjeldende-lover`)
2. Environment variables (`DATASET_FILTER=gjeldende-lover`)
3. `.env` file values
4. Default values in code
