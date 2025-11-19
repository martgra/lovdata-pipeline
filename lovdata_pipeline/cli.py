"""Simple CLI - one command does everything.

Usage:
    lovdata-pipeline process [--force]
"""

import logging
import os
from pathlib import Path

import typer

# Load environment variables from .env file
from dotenv import load_dotenv
from rich.console import Console
from rich.logging import RichHandler

from lovdata_pipeline.progress import RichProgressTracker

load_dotenv()

app = typer.Typer(help="Lovdata Pipeline - Process Norwegian legal documents")
console = Console()

# Configure logging with DEBUG level (progress bars will show main output)
logging.basicConfig(
    level=logging.DEBUG,
    format="%(message)s",
    handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
)


@app.command()
def process(
    force: bool = typer.Option(False, "--force", "-f", help="Reprocess all files"),
    data_dir: str = typer.Option("./data", help="Data directory"),
    dataset: str = typer.Option(
        "gjeldende",
        "--dataset",
        "-d",
        help="Dataset(s) to process. Options: 'gjeldende' (all), 'gjeldende-lover' (laws only), "
        "'gjeldende-sentrale-forskrifter' (regulations only), or '*' (all datasets). "
        "Can use wildcards: 'gjeldende-*' matches all gjeldende datasets.",
    ),
    chunk_max_tokens: int = typer.Option(6800, help="Max tokens per chunk"),
    embedding_model: str = typer.Option("text-embedding-3-large", help="OpenAI model"),
    chroma_path: str = typer.Option("./data/chroma", help="ChromaDB path"),
):
    """Process all documents: sync → chunk → embed → index.

    Runs the complete pipeline atomically per file.

    Examples:
        # Process all current laws and regulations
        lovdata-pipeline process

        # Process only laws (recommended for testing)
        lovdata-pipeline process --dataset gjeldende-lover

        # Process only regulations
        lovdata-pipeline process --dataset gjeldende-sentrale-forskrifter

        # Process all available datasets
        lovdata-pipeline process --dataset "*"

        # Force reprocess everything
        lovdata-pipeline process --force
    """
    # Try to get API key from environment (supports both OPENAI_API_KEY and LOVDATA_OPENAI_API_KEY)
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("LOVDATA_OPENAI_API_KEY")
    if not api_key:
        console.print("[red]Error: OPENAI_API_KEY not set[/red]")
        console.print("Set it in .env file or export OPENAI_API_KEY=sk-...")
        raise typer.Exit(1)

    try:
        from lovdata_pipeline.pipeline import run_pipeline

        console.print("[bold blue]═══ Lovdata Pipeline ═══[/bold blue]")
        console.print(f"Dataset: {dataset}")
        console.print()  # Add blank line before progress bars

        config = {
            "data_dir": Path(data_dir),
            "dataset_filter": dataset,
            "chunk_max_tokens": chunk_max_tokens,
            "embedding_model": embedding_model,
            "openai_api_key": api_key,
            "chroma_path": chroma_path,
            "force": force,
        }

        # Create progress tracker with Rich console
        progress_tracker = RichProgressTracker(console=console)

        # Run pipeline with progress tracking
        result = run_pipeline(config, progress_tracker=progress_tracker)

        # Summary is shown by progress_tracker.show_summary()
        # No need to print duplicate completion message

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
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
