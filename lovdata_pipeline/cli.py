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
    level=logging.DEBUG,
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
):  # pylint: disable=too-many-arguments
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
        console.print()  # Add blank line before progress bars

        # Create progress tracker with Rich console
        progress_tracker = RichProgressTracker(console=console)

        # Run pipeline with progress tracking (convert settings to dict for backward compatibility)
        run_pipeline(settings.to_dict(), progress_tracker=progress_tracker)

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
