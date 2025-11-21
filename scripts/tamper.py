#!/usr/bin/env python3
"""Tamper script for VHS demo - modifies state to demonstrate incremental processing.

This script can:
1. Remove entries from pipeline_state.json to trigger reprocessing
2. Delete JSONL chunk files to simulate data loss
3. Modify file hashes to simulate file changes
"""

import json
import random
from pathlib import Path
from typing import Literal

import typer

app = typer.Typer(help="Tamper with pipeline state to demonstrate functionality")


def load_pipeline_state(state_file: Path) -> dict:
    """Load pipeline_state.json."""
    if not state_file.exists():
        return {"processed": {}, "failed": {}}

    with open(state_file) as f:
        return json.load(f)


def save_pipeline_state(state_file: Path, state: dict):
    """Save pipeline_state.json."""
    with open(state_file, "w") as f:
        json.dump(state, f, indent=2)


@app.command()
def clear_state(
    data_dir: str = typer.Option("./data", help="Data directory"),
    count: int = typer.Option(3, help="Number of entries to remove"),
):
    """Clear some entries from pipeline_state.json to trigger reprocessing.

    This simulates the scenario where some files need to be reprocessed.
    """
    state_file = Path(data_dir) / "pipeline_state.json"
    state = load_pipeline_state(state_file)

    processed = state.get("processed", {})
    if not processed:
        typer.echo("❌ No processed entries to remove")
        raise typer.Exit(1)

    # Select random entries to remove
    doc_ids = list(processed.keys())
    to_remove = random.sample(doc_ids, min(count, len(doc_ids)))

    for doc_id in to_remove:
        del processed[doc_id]
        typer.echo(f"🗑️  Removed {doc_id} from pipeline state")

    save_pipeline_state(state_file, state)
    typer.echo(f"✅ Cleared {len(to_remove)} entries - pipeline will reprocess these files")


@app.command()
def delete_chunks(
    data_dir: str = typer.Option("./data", help="Data directory"),
    count: int = typer.Option(3, help="Number of chunk files to delete"),
):
    """Delete some JSONL chunk files to simulate data loss.

    This demonstrates that the pipeline can recover by reprocessing.
    """
    chunks_dir = Path(data_dir) / "jsonl_chunks"
    if not chunks_dir.exists():
        typer.echo("❌ No jsonl_chunks directory found")
        raise typer.Exit(1)

    chunk_files = list(chunks_dir.glob("*.jsonl"))
    if not chunk_files:
        typer.echo("❌ No chunk files to delete")
        raise typer.Exit(1)

    to_delete = random.sample(chunk_files, min(count, len(chunk_files)))

    for chunk_file in to_delete:
        chunk_file.unlink()
        typer.echo(f"🗑️  Deleted {chunk_file.name}")

    typer.echo(f"✅ Deleted {len(to_delete)} chunk files")


@app.command()
def modify_hash(
    data_dir: str = typer.Option("./data", help="Data directory"),
    count: int = typer.Option(2, help="Number of hashes to modify"),
):
    """Modify file hashes in pipeline_state.json to simulate file changes.

    This will cause the pipeline to detect changes and reprocess those files.
    """
    state_file = Path(data_dir) / "pipeline_state.json"
    state = load_pipeline_state(state_file)

    processed = state.get("processed", {})
    if not processed:
        typer.echo("❌ No processed entries to modify")
        raise typer.Exit(1)

    # Select random entries to modify
    doc_ids = list(processed.keys())
    to_modify = random.sample(doc_ids, min(count, len(doc_ids)))

    for doc_id in to_modify:
        old_hash = processed[doc_id]["hash"]
        # Generate a fake modified hash
        new_hash = old_hash[:-4] + "XXXX"
        processed[doc_id]["hash"] = new_hash
        typer.echo(f"✏️  Modified {doc_id}: {old_hash[:8]}... → {new_hash[:8]}...")

    save_pipeline_state(state_file, state)
    typer.echo(f"✅ Modified {len(to_modify)} hashes - pipeline will detect changes")


@app.command()
def combo(
    data_dir: str = typer.Option("./data", help="Data directory"),
    action: Literal["clear", "modify"] = typer.Option(
        "clear", help="Action to perform: 'clear' or 'modify'"
    ),
):
    """Combined action: modify state and optionally delete chunks."""
    if action == "clear":
        clear_state(data_dir=data_dir, count=2)
    elif action == "modify":
        modify_hash(data_dir=data_dir, count=2)


@app.command()
def status(data_dir: str = typer.Option("./data", help="Data directory")):
    """Show current state statistics."""
    state_file = Path(data_dir) / "pipeline_state.json"
    state = load_pipeline_state(state_file)

    processed_count = len(state.get("processed", {}))
    failed_count = len(state.get("failed", {}))

    chunks_dir = Path(data_dir) / "jsonl_chunks"
    chunk_count = len(list(chunks_dir.glob("*.jsonl"))) if chunks_dir.exists() else 0

    typer.echo("📊 Pipeline State")
    typer.echo(f"   Processed: {processed_count} documents")
    typer.echo(f"   Failed: {failed_count} documents")
    typer.echo(f"   Chunk files: {chunk_count} JSONL files")


if __name__ == "__main__":
    app()
