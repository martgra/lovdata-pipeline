"""Example of using the simplified Lovdata pipeline.

This demonstrates the atomic per-file processing approach where each
document goes through all stages (parse → chunk → embed → index) before
moving to the next document.
"""

from pathlib import Path

from lovdata_pipeline.pipeline import run_pipeline


def main():
    """Run pipeline with custom configuration."""
    print("=" * 70)
    print("Lovdata Pipeline - Atomic Processing Example")
    print("=" * 70)
    print()

    # Configuration
    config = {
        "data_dir": Path("./data"),
        # Options: gjeldende-lover, gjeldende, gjeldende-sentrale-forskrifter, or "*"
        "dataset_filter": "gjeldende-lover",
        "chunk_max_tokens": 6800,
        "embedding_model": "text-embedding-3-large",
        "openai_api_key": "your-api-key-here",  # Set via environment in production
        "chroma_path": "./data/chroma",
        "force": False,  # Only process new/changed files
    }

    print("Configuration:")
    print(f"  Dataset: {config['dataset_filter']}")
    print(f"  Max tokens/chunk: {config['chunk_max_tokens']}")
    print(f"  Embedding model: {config['embedding_model']}")
    print(f"  ChromaDB path: {config['chroma_path']}")
    print(f"  Force reprocess: {config['force']}")
    print()
    print("Available datasets:")
    print("  - gjeldende-lover: Laws only (~2GB, recommended for testing)")
    print("  - gjeldende: All laws + regulations (~10GB)")
    print("  - gjeldende-sentrale-forskrifter: Regulations only (~8GB)")
    print("  - *: All available datasets")
    print()

    # Run pipeline
    print("Starting pipeline...")
    print()

    result = run_pipeline(config)

    print()
    print("=" * 70)
    print("Pipeline Complete!")
    print("=" * 70)
    print(f"Processed: {result['processed']} documents")
    print(f"Failed: {result['failed']} documents")
    print()
    print("Each document was atomically:")
    print("  1. Parsed (XML → articles)")
    print("  2. Chunked (articles → token-sized pieces)")
    print("  3. Embedded (text → vectors via OpenAI)")
    print("  4. Indexed (vectors → ChromaDB)")


if __name__ == "__main__":
    main()
