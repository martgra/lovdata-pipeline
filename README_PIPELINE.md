# Lovdata Pipeline

A production-ready Dagster pipeline for ingesting Norwegian legal documents from Lovdata, generating embeddings, and loading them into ChromaDB for semantic search.

## Features

- **Automated Sync**: Leverages the [`lovlig`](https://github.com/martgra/lovlig) library for efficient downloading and change detection
- **Intelligent Chunking**: Parses XML documents at the legal article (§) level using lxml
- **Embeddings Generation**: OpenAI text-embedding-3-large with batching and rate limiting
- **Vector Storage**: ChromaDB for efficient semantic search
- **Observability**: Langfuse integration for cost tracking and performance monitoring
- **Incremental Processing**: Only processes changed files for efficiency
- **Production Ready**: Comprehensive error handling, retry logic, and testing

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌───────────────┐
│   Lovdata   │────▶│    lovlig    │────▶│ XML Documents │
│     API     │     │   Library    │     │  (extracted)  │
└─────────────┘     └──────────────┘     └───────────────┘
                                                 │
                                                 ▼
                    ┌────────────────────────────────────────┐
                    │         Dagster Pipeline               │
                    │                                        │
                    │  ┌──────────────┐                      │
                    │  │  Ingestion   │                      │
                    │  │   - lovdata_sync                    │
                    │  │   - changed_legal_documents         │
                    │  │   - parsed_legal_chunks             │
                    │  └───────┬──────┘                      │
                    │          │                             │
                    │          ▼                             │
                    │  ┌──────────────┐                      │
                    │  │Transformation│                      │
                    │  │   - document_embeddings             │
                    │  │   - OpenAI API                      │
                    │  │   - Langfuse observability          │
                    │  └───────┬──────┘                      │
                    │          │                             │
                    │          ▼                             │
                    │  ┌──────────────┐                      │
                    │  │   Loading    │                      │
                    │  │   - vector_database                 │
                    │  │   - handle_deleted_documents        │
                    │  └───────┬──────┘                      │
                    └──────────┼────────────────────────────┘
                               │
                               ▼
                    ┌──────────────────┐
                    │    ChromaDB      │
                    │ Vector Database  │
                    └──────────────────┘
```

## Installation

### Prerequisites

- Python 3.11+
- Git
- OpenAI API key
- Langfuse account (optional but recommended)

### Using UV (Recommended)

```bash
# Clone the repository
git clone <repository-url>
cd lovdata-pipeline

# Install dependencies with UV
uv pip install -e ".[dev,test]"
```

### Using pip

```bash
# Clone the repository
git clone <repository-url>
cd lovdata-pipeline

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e ".[dev,test]"
```

### Using Docker

```bash
# Build the Docker image
docker-compose build

# Start the pipeline
docker-compose up
```

## Configuration

1. **Copy the example environment file:**

```bash
cp .env.example .env
```

2. **Edit `.env` with your configuration:**

```bash
# Required
OPENAI_API_KEY=sk-your-api-key-here

# Optional (for observability)
LANGFUSE_PUBLIC_KEY=pk-lf-your-public-key
LANGFUSE_SECRET_KEY=sk-lf-your-secret-key
LANGFUSE_HOST=https://cloud.langfuse.com
```

3. **Directory structure** (created automatically):

```
data/
├── raw/           # Downloaded ZIP files from Lovdata
├── extracted/     # Extracted XML documents
├── chromadb/      # ChromaDB persistent storage
└── state.json     # lovlig state tracking file
```

## Usage

### Development Mode

Start the Dagster UI for development:

```bash
dagster dev -m lovdata_pipeline
```

Then open http://localhost:3000 in your browser.

### Running the Pipeline

#### Via Dagster UI

1. Navigate to http://localhost:3000
2. Go to "Assets" tab
3. Click "Materialize all" to run the complete pipeline

#### Via CLI

```bash
# Run the complete pipeline
dagster job execute -m lovdata_pipeline -j lovdata_processing_job

# Run only the sync step
dagster job execute -m lovdata_pipeline -j lovdata_sync_only_job
```

### Scheduled Execution

The pipeline includes a daily schedule (disabled by default):

1. In Dagster UI, go to "Schedules"
2. Enable `daily_lovdata_schedule` (runs daily at 2 AM)

## Pipeline Components

### Assets

#### Ingestion (`lovdata_pipeline/assets/ingestion.py`)

- **`lovdata_sync`**: Syncs Lovdata datasets using the lovlig library
- **`changed_legal_documents`**: Identifies files that need processing (added/modified)
- **`parsed_legal_chunks`**: Parses XML documents into structured legal chunks

#### Transformation (`lovdata_pipeline/assets/transformation.py`)

- **`document_embeddings`**: Generates embeddings using OpenAI with batching and Langfuse observability

#### Loading (`lovdata_pipeline/assets/loading.py`)

- **`vector_database`**: Upserts embeddings to ChromaDB
- **`handle_deleted_documents`**: Removes chunks for deleted files

### Resources

#### `LovligResource`

Wraps the lovlig library for:

- Syncing Lovdata datasets
- Querying change state
- Managing file paths

#### `ChromaDBResource`

Manages ChromaDB operations:

- Collection creation and management
- Batch upserts
- Document deletion

#### `OpenAIResource`

Dagster's built-in OpenAI resource for embeddings generation.

### Parser

#### `LovdataXMLParser`

Parses Lovdata XML documents:

- Extracts chunks at `legalArticle` (§) or `legalP` (paragraph) level
- Preserves hierarchical context (chapter, section, paragraph)
- Generates comprehensive metadata

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=lovdata_pipeline --cov-report=html

# Run specific test file
pytest tests/test_parser.py
```

## Monitoring and Observability

### Langfuse

The pipeline integrates with Langfuse for:

- Cost tracking per embedding batch
- Performance monitoring
- Error tracking
- Token usage analytics

Access your Langfuse dashboard at https://cloud.langfuse.com to view:

- Total embeddings generated
- Cost per document
- Batch processing times
- Failure rates

### Dagster Logs

All pipeline execution logs are available in the Dagster UI:

1. Navigate to "Runs"
2. Click on any run to view detailed logs
3. Each asset logs processing statistics and errors

## Performance Tuning

### Embedding Generation

Adjust batch sizes in `.env`:

```bash
# Number of texts per OpenAI API request
BATCH_SIZE_EMBEDDINGS=100

# Delay between batches (seconds)
RATE_LIMIT_DELAY=1.0
```

### ChromaDB

Modify collection settings in `resources/chromadb_resource.py`:

```python
metadata={
    "hnsw:space": "cosine",
    "hnsw:batch_size": 100,
    "hnsw:sync_threshold": 1000,
}
```

## Troubleshooting

### Common Issues

**Import errors for lxml:**

```bash
# Install system dependencies
sudo apt-get install libxml2-dev libxslt-dev
pip install --force-reinstall lxml
```

**lovlig not found:**

```bash
# Ensure lovlig is installed from GitHub
pip install git+https://github.com/martgra/lovlig.git
```

**ChromaDB persistence issues:**

```bash
# Ensure data directory exists and has write permissions
mkdir -p data/chromadb
chmod -R 755 data/
```

**OpenAI rate limits:**

- Increase `RATE_LIMIT_DELAY` in `.env`
- Reduce `BATCH_SIZE_EMBEDDINGS`
- Use OpenAI Batch API for non-urgent processing

## Project Structure

```
lovdata-pipeline/
├── lovdata_pipeline/
│   ├── __init__.py
│   ├── __main__.py
│   ├── definitions.py          # Dagster definitions
│   ├── assets/
│   │   ├── ingestion.py        # Sync and parsing assets
│   │   ├── transformation.py   # Embedding generation
│   │   └── loading.py          # ChromaDB operations
│   ├── resources/
│   │   ├── lovlig_resource.py  # lovlig integration
│   │   └── chromadb_resource.py # ChromaDB integration
│   ├── parsers/
│   │   └── lovdata_xml_parser.py # XML parsing logic
│   └── utils/
├── tests/
│   ├── conftest.py             # Test fixtures
│   ├── test_parser.py          # Parser tests
│   └── test_assets.py          # Asset tests
├── data/                       # Data directories (gitignored)
├── dagster_home/               # Dagster storage
├── .env.example                # Example environment variables
├── pyproject.toml              # Project dependencies
├── Dockerfile                  # Docker image
├── docker-compose.yml          # Docker Compose config
└── README.md                   # This file
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests (`pytest`)
5. Run linters (`ruff check lovdata_pipeline/`)
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

## License

This project is licensed under the terms specified in the LICENSE file.

## Acknowledgments

- [lovlig](https://github.com/martgra/lovlig) for Lovdata API integration
- [Dagster](https://dagster.io/) for orchestration
- [ChromaDB](https://www.trychroma.com/) for vector storage
- [Langfuse](https://langfuse.com/) for observability
- [Lovdata](https://lovdata.no/) for providing legal documents under NLOD 2.0 license

## Support

For issues, questions, or contributions:

- Open an issue on GitHub
- Check existing documentation in `docs/`
- Review Dagster logs in the UI

---

Built with ❤️ for Norwegian legal document processing
