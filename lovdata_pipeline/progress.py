"""Progress tracking abstraction for the Lovdata pipeline.

This module provides a clean separation of concerns for progress tracking,
allowing the pipeline to report progress without coupling to specific
progress bar implementations.
"""

import logging
from typing import Any, Protocol

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
)

logger = logging.getLogger(__name__)


class ProgressTracker(Protocol):
    """Protocol for progress tracking implementations.

    This defines the interface that all progress trackers must implement,
    allowing for different implementations (Rich, simple console, silent, etc.)
    """

    def start_stage(self, stage: str, description: str) -> None:
        """Start a new pipeline stage (sync, process, cleanup, etc.)."""
        ...

    def end_stage(self, stage: str) -> None:
        """End the current pipeline stage."""
        ...

    def start_file_processing(self, total_files: int) -> None:
        """Start tracking file processing progress."""
        ...

    def update_file(self, doc_id: str, current: int, total: int) -> None:
        """Update progress for current file being processed."""
        ...

    def end_file_processing(self) -> None:
        """End file processing progress tracking."""
        ...

    def start_embedding(self, total_chunks: int) -> None:
        """Start tracking embedding progress within a file."""
        ...

    def update_embedding(self, chunks_embedded: int, total_chunks: int) -> None:
        """Update embedding progress."""
        ...

    def end_embedding(self) -> None:
        """End embedding progress tracking."""
        ...

    def log_success(self, doc_id: str, chunk_count: int) -> None:
        """Log successful processing of a document."""
        ...

    def log_warning(self, message: str) -> None:
        """Log a warning message."""
        ...

    def log_error(self, doc_id: str, error: str) -> None:
        """Log an error for a document."""
        ...

    def show_summary(self, summary: dict[str, Any]) -> None:
        """Display final summary statistics."""
        ...


class NoOpProgressTracker:
    """Progress tracker that does nothing.

    Useful for testing or when progress tracking is not desired.
    """

    def start_stage(self, stage: str, description: str) -> None:
        """Start a new stage (no-op)."""
        pass

    def end_stage(self, stage: str) -> None:
        """End the current stage (no-op)."""
        pass

    def start_file_processing(self, total_files: int) -> None:
        """Start file processing stage (no-op)."""
        pass

    def update_file(self, doc_id: str, current: int, total: int) -> None:
        """Update file processing progress (no-op)."""
        pass

    def end_file_processing(self) -> None:
        """End file processing stage (no-op)."""
        pass

    def start_embedding(self, total_chunks: int) -> None:
        """Start embedding stage (no-op)."""
        pass

    def update_embedding(self, chunks_embedded: int, total_chunks: int) -> None:
        """Update embedding progress (no-op)."""
        pass

    def end_embedding(self) -> None:
        """End embedding stage (no-op)."""
        pass

    def log_success(self, doc_id: str, chunk_count: int) -> None:
        """Log successful processing (no-op)."""
        pass

    def log_warning(self, message: str) -> None:
        """Log warning message (no-op)."""
        pass

    def log_error(self, doc_id: str, error: str) -> None:
        """Log error message (no-op)."""
        pass

    def show_summary(self, summary: dict[str, Any]) -> None:
        """Show processing summary (no-op)."""
        pass


class RichProgressTracker:
    """Progress tracker using Rich library for beautiful progress bars.

    Provides multi-level progress tracking with automatic lifecycle management.
    """

    def __init__(self, console: Console | None = None):
        """Initialize the Rich progress tracker."""
        self.console = console or Console()
        self._file_progress: Progress | None = None
        self._embedding_progress: Progress | None = None
        self.current_stage: str | None = None
        self._file_task_id: Any | None = None
        self._embedding_task_id: Any | None = None

    def _get_or_create_progress(self, attr_name: str, create_fn: callable) -> tuple[Progress, bool]:
        """Get existing progress or create new one. Returns (progress, was_created)."""
        progress = getattr(self, attr_name)
        if progress is None:
            progress = create_fn()
            setattr(self, attr_name, progress)
            progress.start()
            return progress, True
        return progress, False

    def _cleanup_progress(self, attr_name: str, task_id_attr: str) -> None:
        """Stop and clean up a progress instance."""
        progress = getattr(self, attr_name)
        if progress is not None:
            progress.stop()
            setattr(self, attr_name, None)
            setattr(self, task_id_attr, None)

    def start_stage(self, stage: str, description: str) -> None:
        """Start a new pipeline stage."""
        self.current_stage = stage
        self.console.print(f"\n[bold cyan]═══ {description} ═══[/bold cyan]")

    def end_stage(self, stage: str) -> None:
        """End the current pipeline stage."""
        if stage == self.current_stage:
            self.current_stage = None

    def start_file_processing(self, total_files: int) -> None:
        """Start tracking file processing progress."""
        progress, _ = self._get_or_create_progress(
            "_file_progress",
            lambda: Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]{task.description}"),
                BarColumn(bar_width=40),
                MofNCompleteColumn(),
                console=self.console,
                transient=False,
            ),
        )
        self._file_task_id = progress.add_task(f"Processing {total_files} files", total=total_files)

    def update_file(self, doc_id: str, current: int, total: int) -> None:
        """Update progress for current file being processed."""
        if self._file_progress and self._file_task_id is not None:
            self._file_progress.update(
                self._file_task_id,
                completed=current,
                description=f"Processing: {doc_id[:50]}...",
            )

    def end_file_processing(self) -> None:
        """End file processing progress tracking."""
        if self._file_progress and self._file_task_id is not None:
            self._file_progress.update(self._file_task_id, visible=False)
        self._cleanup_progress("_file_progress", "_file_task_id")

    def start_embedding(self, total_chunks: int) -> None:
        """Start tracking embedding progress within a file."""
        progress, _ = self._get_or_create_progress(
            "_embedding_progress",
            lambda: Progress(
                SpinnerColumn(),
                TextColumn("{task.description}"),
                console=self.console,
                transient=False,
            ),
        )
        self._embedding_task_id = progress.add_task("[yellow]  └─ Embedding chunks", total=None)

    def update_embedding(self, chunks_embedded: int, total_chunks: int) -> None:
        """Update embedding progress."""
        if self._embedding_progress and self._embedding_task_id is not None:
            self._embedding_progress.update(
                self._embedding_task_id,
                completed=chunks_embedded,
                total=total_chunks,
                description=f"[yellow]  └─ Embedding chunks ({chunks_embedded}/{total_chunks})",
            )

    def end_embedding(self) -> None:
        """End embedding progress tracking."""
        if self._embedding_progress and self._embedding_task_id is not None:
            self._embedding_progress.remove_task(self._embedding_task_id)
        self._cleanup_progress("_embedding_progress", "_embedding_task_id")

    def log_success(self, doc_id: str, chunk_count: int) -> None:
        """Log successful processing of a document."""
        logger.debug(f"✓ {doc_id}: {chunk_count} chunks")

    def log_warning(self, message: str) -> None:
        """Log a warning message."""
        self.console.print(f"[yellow]⚠ {message}[/yellow]")
        logger.warning(message)

    def log_error(self, doc_id: str, error: str) -> None:
        """Log an error for a document."""
        self.console.print(f"[red]✗ {doc_id}: {error}[/red]")
        logger.error(f"Failed to process {doc_id}: {error}")

    def show_summary(self, summary: dict[str, Any]) -> None:
        """Display final summary statistics."""
        self.console.print("\n[bold cyan]═══ Summary ═══[/bold cyan]")
        self.console.print(f"[green]✓[/green] Processed: {summary.get('processed', 0)} documents")
        self.console.print(f"[red]✗[/red] Failed: {summary.get('failed', 0)} documents")
        if summary.get("removed", 0) > 0:
            self.console.print(f"[yellow]🗑️[/yellow] Removed: {summary['removed']} documents")
