"""Simple CLI - one command does everything.

Usage:
    lovdata-pipeline process [--force]
"""

import logging
from pathlib import Path

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.logging import RichHandler

from lovdata_pipeline.config.settings import PipelineSettings
from lovdata_pipeline.progress import RichProgressTracker

app = typer.Typer(help="Lovdata Pipeline - Process Norwegian legal documents")
console = Console()

# Configure logging with DEBUG level (progress bars will show main output)
logging.basicConfig(
    level=logging.ERROR,
    format="%(message)s",
    handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
)


@app.command()
def process(
    force: bool = typer.Option(None, "--force", "-f", help="Reprocess all files"),
    data_dir: str = typer.Option(None, help="Data directory"),
    dataset: str = typer.Option(
        None,
        "--dataset",
        "-d",
        help="Dataset(s) to process. Options: 'gjeldende' (all), 'gjeldende-lover' (laws only), "
        "'gjeldende-sentrale-forskrifter' (regulations only), or '*' (all datasets). "
        "Can use wildcards: 'gjeldende-*' matches all gjeldende datasets.",
    ),
    chunk_max_tokens: int = typer.Option(None, help="Max tokens per chunk"),
    embedding_model: str = typer.Option(None, help="OpenAI model"),
    chroma_path: str = typer.Option(None, help="ChromaDB path"),
    storage: str = typer.Option(
        None,
        "--storage",
        "-s",
        help="Storage type: 'chroma' (default) or 'jsonl'",
    ),
    limit: int = typer.Option(
        None,
        "--limit",
        "-l",
        help="Limit number of files to process (for testing)",
    ),
):  # pylint: disable=too-many-arguments
    """Process all documents: sync → chunk → embed → index.

    Runs the complete pipeline atomically per file.

    Examples:
        # Process all current laws and regulations
        lovdata-pipeline process

        # Process only laws (recommended for testing)
        lovdata-pipeline process --dataset gjeldende-lover

        # Process with JSONL storage instead of ChromaDB
        lovdata-pipeline process --storage jsonl

        # Test with first 10 files only
        lovdata-pipeline process --limit 10

        # Process only regulations
        lovdata-pipeline process --dataset gjeldende-sentrale-forskrifter

        # Process all available datasets
        lovdata-pipeline process --dataset "*"

        # Force reprocess everything
        lovdata-pipeline process --force
    """
    try:
        # Load settings from environment with CLI overrides
        settings_kwargs = {}
        if force is not None:
            settings_kwargs["force"] = force
        if data_dir is not None:
            settings_kwargs["data_dir"] = data_dir
        if dataset is not None:
            settings_kwargs["dataset_filter"] = dataset
        if chunk_max_tokens is not None:
            settings_kwargs["chunk_max_tokens"] = chunk_max_tokens
        if embedding_model is not None:
            settings_kwargs["embedding_model"] = embedding_model
        if chroma_path is not None:
            settings_kwargs["chroma_path"] = chroma_path
        if storage is not None:
            settings_kwargs["storage_type"] = storage
        if limit is not None:
            settings_kwargs["limit"] = limit

        # Load and validate settings
        settings = PipelineSettings(**settings_kwargs)

    except ValidationError as e:
        console.print("[red]Configuration Error:[/red]")
        for error in e.errors():
            field = " → ".join(str(x) for x in error["loc"])
            console.print(f"  {field}: {error['msg']}")
        console.print("\n[yellow]Tip:[/yellow] Set OPENAI_API_KEY in .env file or environment")
        raise typer.Exit(1) from e

    try:
        from lovdata_pipeline.pipeline import run_pipeline

        console.print("[bold blue]═══ Lovdata Pipeline ═══[/bold blue]")
        console.print(f"Dataset: {settings.dataset_filter}")
        console.print(f"Storage: {settings.storage_type}")
        if settings.limit:
            console.print(f"[yellow]Limit: {settings.limit} files (testing mode)[/yellow]")
        console.print()  # Add blank line before progress bars

        # Create progress tracker with Rich console
        progress_tracker = RichProgressTracker(console=console)

        # Run pipeline with progress tracking (convert settings to dict for backward compatibility)
        run_pipeline(settings, progress_tracker=progress_tracker)

        # Summary is shown by progress_tracker.show_summary()
        # No need to print duplicate completion message

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def migrate(
    source: str = typer.Option(..., "--source", "-s", help="Source storage: 'chroma' or 'jsonl'"),
    target: str = typer.Option(..., "--target", "-t", help="Target storage: 'chroma' or 'jsonl'"),
    data_dir: str = typer.Option("./data", help="Data directory"),
    chroma_path: str = typer.Option(None, help="ChromaDB path (if different from default)"),
    jsonl_path: str = typer.Option(None, help="JSONL storage path (if different from default)"),
    batch_size: int = typer.Option(1000, help="Batch size for migration"),
):
    """Migrate chunks between storage backends.

    Examples:
        # Migrate from ChromaDB to JSONL
        lovdata-pipeline migrate --source chroma --target jsonl

        # Migrate from JSONL to ChromaDB
        lovdata-pipeline migrate --source jsonl --target chroma

        # Specify custom paths
        lovdata-pipeline migrate -s chroma -t jsonl --jsonl-path ./backup
    """
    try:
        from pathlib import Path

        # Validate storage types
        if source not in ["chroma", "jsonl"]:
            console.print(f"[red]Invalid source storage: {source}[/red]")
            console.print("Must be 'chroma' or 'jsonl'")
            raise typer.Exit(1)

        if target not in ["chroma", "jsonl"]:
            console.print(f"[red]Invalid target storage: {target}[/red]")
            console.print("Must be 'chroma' or 'jsonl'")
            raise typer.Exit(1)

        if source == target:
            console.print("[red]Source and target must be different[/red]")
            raise typer.Exit(1)

        # Set default paths
        data_path = Path(data_dir)
        chroma_storage_path = chroma_path or str(data_path / "chroma")
        jsonl_storage_path = jsonl_path or str(data_path / "jsonl_chunks")

        console.print("[bold blue]═══ Storage Migration ═══[/bold blue]")
        console.print(f"Source: {source}")
        console.print(f"Target: {target}")
        console.print()

        # Import storage implementations
        import chromadb

        from lovdata_pipeline.domain.models import EnrichedChunk
        from lovdata_pipeline.infrastructure.chroma_vector_store import ChromaVectorStoreRepository
        from lovdata_pipeline.infrastructure.jsonl_vector_store import JsonlVectorStoreRepository

        # Initialize source and target stores
        if source == "chroma":
            console.print(f"Loading from ChromaDB: {chroma_storage_path}")
            client = chromadb.PersistentClient(path=chroma_storage_path)
            try:
                collection = client.get_collection(name="legal_docs")
            except Exception as e:
                console.print(f"[red]Failed to load ChromaDB collection: {e}[/red]")
                raise typer.Exit(1) from e

            total_chunks = collection.count()
            console.print(f"Found {total_chunks} chunks to migrate")

            target_store = JsonlVectorStoreRepository(Path(jsonl_storage_path))
            console.print(f"Target JSONL directory: {jsonl_storage_path}")

            # Migrate in batches
            offset = 0
            migrated = 0

            while offset < total_chunks:
                result = collection.get(
                    limit=batch_size,
                    offset=offset,
                    include=["embeddings", "metadatas", "documents"],
                )

                batch_size_actual = len(result["ids"])
                if batch_size_actual == 0:
                    break

                # Convert to EnrichedChunk objects
                chunks = []
                for i in range(batch_size_actual):
                    try:
                        chunk = EnrichedChunk(
                            chunk_id=result["ids"][i],
                            document_id=result["metadatas"][i].get("document_id", "unknown"),
                            dataset_name=result["metadatas"][i].get("dataset_name", ""),
                            content=result["documents"][i],
                            token_count=int(result["metadatas"][i].get("token_count", 0)),
                            section_heading=result["metadatas"][i].get("section_heading", ""),
                            absolute_address=result["metadatas"][i].get("absolute_address", ""),
                            split_reason=result["metadatas"][i].get("split_reason", "none"),
                            parent_chunk_id=result["metadatas"][i].get("parent_chunk_id"),
                            source_hash=result["metadatas"][i].get("source_hash", ""),
                            embedding=list(result["embeddings"][i]),
                            embedding_model=result["metadatas"][i].get(
                                "embedding_model", "unknown"
                            ),
                            embedded_at=result["metadatas"][i].get("embedded_at", ""),
                        )
                        chunks.append(chunk)
                    except Exception:
                        console.print(
                            "[yellow]Warning: Failed to convert chunk"
                            " {result['ids'][i]}: {e}[/yellow]"
                        )

                # Write to target
                target_store.upsert_chunks(chunks)
                migrated += len(chunks)
                console.print(f"Migrated {migrated}/{total_chunks} chunks...")

                offset += batch_size_actual

        else:  # source == "jsonl"
            console.print(f"Loading from JSONL: {jsonl_storage_path}")
            source_store = JsonlVectorStoreRepository(Path(jsonl_storage_path))

            total_chunks = source_store.count()
            console.print(f"Found {total_chunks} chunks to migrate")

            # Initialize ChromaDB target
            console.print(f"Target ChromaDB: {chroma_storage_path}")
            client = chromadb.PersistentClient(path=chroma_storage_path)
            collection = client.get_or_create_collection(
                name="legal_docs",
                metadata={"description": "Norwegian legal documents"},
            )
            target_store = ChromaVectorStoreRepository(collection)

            # Migrate each hash file
            migrated = 0
            hashes = source_store.list_hashes()

            for hash_val in hashes:
                chunks = source_store.get_chunks_by_hash(hash_val)
                target_store.upsert_chunks(chunks)
                migrated += len(chunks)
                console.print(f"Migrated {migrated}/{total_chunks} chunks from {hash_val}.jsonl...")

        console.print()
        console.print("[green]✓ Migration complete![/green]")
        console.print(f"Migrated {migrated} chunks from {source} to {target}")

    except Exception as e:
        console.print(f"[red]Migration failed: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def status(data_dir: str = typer.Option("./data", help="Data directory")):
    """Show pipeline status."""
    try:
        from lovdata_pipeline.state import ProcessingState

        state = ProcessingState(Path(data_dir) / "pipeline_state.json")
        stats = state.stats()

        console.print("[bold]Pipeline Status[/bold]")
        console.print(f"  Processed: {stats['processed']} documents")
        console.print(f"  Failed: {stats['failed']} documents")
        console.print(f"  Indexed: {stats['total_vectors']} vectors")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from e


def main():
    """Entry point."""
    app()


if __name__ == "__main__":
    main()
