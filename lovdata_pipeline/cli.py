"""Simple CLI to run the Lovdata pipeline without Dagster.

This provides a direct command-line interface to execute pipeline steps.
Uses typer for modern CLI with automatic help generation and type validation.
"""

import logging

import typer
from rich.console import Console
from rich.logging import RichHandler

from lovdata_pipeline import pipeline_steps

# Configure rich logging
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
)
logger = logging.getLogger(__name__)

# Create typer app
app = typer.Typer(
    name="lovdata-pipeline",
    help="Lovdata Pipeline CLI - Process Norwegian legal documents",
    add_completion=False,
)

console = Console()


@app.command()
def sync(
    force_download: bool = typer.Option(
        False, "--force-download", "-f", help="Force re-download of all datasets"
    ),
):
    """Sync datasets from Lovdata.

    Downloads and extracts legal document archives from Lovdata API.
    """
    try:
        console.print("[bold blue]═══ Running Lovdata Sync ═══[/bold blue]")
        stats = pipeline_steps.sync_datasets(force_download=force_download)
        console.print(f"[green]✓[/green] Sync complete: {stats}")
    except Exception as e:
        logger.error(f"Sync failed: {e}", exc_info=True)
        raise typer.Exit(code=1) from e


@app.command()
def chunk(
    force_reprocess: bool = typer.Option(
        False, "--force-reprocess", "-f", help="Force reprocessing of all files"
    ),
):
    """Chunk XML documents into legal articles.

    Parses XML files and splits them into meaningful chunks for embedding.
    """
    try:
        console.print("[bold blue]═══ Running Document Chunking ═══[/bold blue]")
        changed_paths = pipeline_steps.get_changed_file_paths(
            stage="chunking", force_reprocess=force_reprocess
        )
        removed_metadata = pipeline_steps.get_removed_file_metadata()
        stats = pipeline_steps.chunk_documents(changed_paths, removed_metadata)
        console.print(f"[green]✓[/green] Chunking complete: {stats}")
    except Exception as e:
        logger.error(f"Chunking failed: {e}", exc_info=True)
        raise typer.Exit(code=1) from e


@app.command()
def embed(
    force_reembed: bool = typer.Option(
        False, "--force-reembed", "-f", help="Force re-embedding of all chunks"
    ),
):
    """Generate embeddings for chunks using OpenAI.

    Creates vector embeddings for each chunk using OpenAI's embedding API.
    """
    try:
        console.print("[bold blue]═══ Running Chunk Embedding ═══[/bold blue]")
        changed_paths = pipeline_steps.get_changed_file_paths(
            stage="embedding", force_reprocess=force_reembed
        )
        stats = pipeline_steps.embed_chunks(changed_paths, force_reembed=force_reembed)
        console.print(f"[green]✓[/green] Embedding complete: {stats}")
    except Exception as e:
        logger.error(f"Embedding failed: {e}", exc_info=True)
        raise typer.Exit(code=1) from e


@app.command()
def index():
    """Index embeddings in ChromaDB vector database.

    Stores vector embeddings in ChromaDB for semantic search.
    """
    try:
        console.print("[bold blue]═══ Running Vector Indexing ═══[/bold blue]")
        changed_paths = pipeline_steps.get_changed_file_paths(stage="indexing")
        removed_metadata = pipeline_steps.get_removed_file_metadata()
        stats = pipeline_steps.index_embeddings(changed_paths, removed_metadata)
        console.print(f"[green]✓[/green] Indexing complete: {stats}")
    except Exception as e:
        logger.error(f"Indexing failed: {e}", exc_info=True)
        raise typer.Exit(code=1) from e


@app.command()
def reconcile():
    """Reconcile index with lovlig state.

    Detect and remove ghost documents from the index that no longer exist
    in the source data.
    """
    try:
        console.print("[bold blue]═══ Running Index Reconciliation ═══[/bold blue]")
        stats = pipeline_steps.reconcile_index()
        console.print(f"[green]✓[/green] Reconciliation complete: {stats}")
    except Exception as e:
        logger.error(f"Reconciliation failed: {e}", exc_info=True)
        raise typer.Exit(code=1) from e


@app.command()
def full(
    force_download: bool = typer.Option(
        False, "--force-download", help="Force re-download of all datasets"
    ),
    force_reprocess: bool = typer.Option(
        False, "--force-reprocess", help="Force reprocessing of all files"
    ),
):
    """Run the complete pipeline end-to-end.

    Executes all steps: sync → chunk → embed → index
    """
    try:
        console.print("[bold magenta]═══ Running Full Pipeline ═══[/bold magenta]")

        # Sync
        console.print("\n[bold blue]Step 1/4: Sync[/bold blue]")
        stats = pipeline_steps.sync_datasets(force_download=force_download)
        console.print(f"[green]✓[/green] {stats}")

        # Chunk
        console.print("\n[bold blue]Step 2/4: Chunk[/bold blue]")
        changed_paths = pipeline_steps.get_changed_file_paths(
            stage="chunking", force_reprocess=force_reprocess
        )
        removed_metadata = pipeline_steps.get_removed_file_metadata()
        stats = pipeline_steps.chunk_documents(changed_paths, removed_metadata)
        console.print(f"[green]✓[/green] {stats}")

        # Embed
        console.print("\n[bold blue]Step 3/4: Embed[/bold blue]")
        changed_paths = pipeline_steps.get_changed_file_paths(
            stage="embedding", force_reprocess=force_reprocess
        )
        stats = pipeline_steps.embed_chunks(changed_paths, force_reembed=force_reprocess)
        console.print(f"[green]✓[/green] {stats}")

        # Index
        console.print("\n[bold blue]Step 4/4: Index[/bold blue]")
        changed_paths = pipeline_steps.get_changed_file_paths(
            stage="indexing", force_reprocess=force_reprocess
        )
        removed_metadata = pipeline_steps.get_removed_file_metadata()
        stats = pipeline_steps.index_embeddings(changed_paths, removed_metadata)
        console.print(f"[green]✓[/green] {stats}")

        console.print("\n[bold green]═══ Pipeline Complete ═══[/bold green]")
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        raise typer.Exit(code=1) from e


def main():
    """Main CLI entry point."""
    app()


if __name__ == "__main__":
    main()
