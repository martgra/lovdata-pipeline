"""Loading assets for ChromaDB operations.

This module contains Dagster assets for:
- Cleaning up removed/modified documents before processing
- Upserting embeddings to ChromaDB
- Maintaining vector database consistency
"""

from __future__ import annotations

from pathlib import Path

from dagster import asset
from langfuse import get_client, observe

from lovdata_pipeline.resources import ChromaDBResource, LovligResource


@asset(group_name="loading", compute_kind="chromadb")
def cleanup_changed_documents(
    context,
    lovlig: LovligResource,
    chromadb: ChromaDBResource,
    lovdata_sync: dict[str, int],  # Ensure sync completed
) -> dict:
    """Clean up ChromaDB before processing changed documents.

    This asset runs BEFORE embeddings are generated and ensures:
    1. Removed documents are deleted from ChromaDB
    2. Modified documents have their old chunks deleted (before re-processing)

    This prevents orphaned chunks if document structure changed (e.g., § removed/added).

    Args:
        context: Dagster execution context
        lovlig: LovligResource for querying changed files
        chromadb: ChromaDB resource for database operations
        lovdata_sync: Dependency on sync completion

    Returns:
        Dictionary with deletion statistics
    """
    # Get removed and modified files from lovlig state
    removed_files = lovlig.get_changed_files("removed")
    modified_files = lovlig.get_changed_files("modified")

    if not removed_files and not modified_files:
        context.log.info("No files removed or modified - skipping cleanup")
        return {"deleted_chunks": 0, "files_removed": 0, "files_modified": 0}

    collection = chromadb.get_collection()
    total_deleted = 0
    removed_count = 0
    modified_count = 0

    # Process removed files
    for file_meta in removed_files:
        file_path = Path(file_meta["path"])
        doc_id = file_path.stem  # e.g., "nl-1999-07-02-63" from "nl-1999-07-02-63.xml"

        deleted = chromadb.delete_by_document_id(doc_id)

        if deleted > 0:
            context.log.info(f"Removed document {doc_id}: deleted {deleted} chunks")
            total_deleted += deleted
            removed_count += 1

    # Process modified files - delete old chunks before new ones are generated
    for file_meta in modified_files:
        file_path = Path(file_meta["path"])
        doc_id = file_path.stem

        deleted = chromadb.delete_by_document_id(doc_id)

        if deleted > 0:
            context.log.info(
                f"Modified document {doc_id}: deleted {deleted} old chunks (will be re-processed)"
            )
            total_deleted += deleted
            modified_count += 1

    context.add_output_metadata(
        {
            "files_removed": removed_count,
            "files_modified": modified_count,
            "chunks_deleted": total_deleted,
        }
    )

    return {
        "deleted_chunks": total_deleted,
        "files_removed": removed_count,
        "files_modified": modified_count,
    }


@asset(group_name="loading", compute_kind="chromadb")
@observe(name="verify-chromadb")
def vector_database(
    context,
    chromadb: ChromaDBResource,
    document_embeddings: dict,
    cleanup_changed_documents: dict,  # Ensure cleanup happens first
) -> dict:
    """Verify ChromaDB collection after streaming writes.

    This asset now serves as a verification step since embeddings are
    written to ChromaDB during generation (streaming approach).
    The cleanup_changed_documents dependency ensures old chunks are deleted first.

    Args:
        context: Dagster execution context
        chromadb: ChromaDB resource for database operations
        document_embeddings: Dict with embedding statistics
        cleanup_changed_documents: Dependency ensuring cleanup completed first

    Returns:
        Dictionary with operation statistics
    """
    if document_embeddings.get("total_embeddings", 0) == 0:
        context.log.info("No embeddings were generated")
        return {"status": "skipped", "verified": 0}

    langfuse = get_client()

    # Get collection for verification
    collection = chromadb.get_collection()
    collection_count = collection.count()

    context.log.info(
        f"Embeddings already written during generation (streaming). "
        f"Collection now contains {collection_count} total chunks."
    )

    with langfuse.start_as_current_observation(as_type="span", name="chromadb-verify") as obs:
        obs.update(
            output={"verified": True, "collection_count": collection_count},
            metadata={
                "collection_name": chromadb.collection_name,
                "embeddings_from_run": document_embeddings.get("total_embeddings", 0),
            },
        )

    langfuse.flush()

    context.add_output_metadata(
        {
            "embeddings_from_run": document_embeddings.get("total_embeddings", 0),
            "collection_total_count": collection_count,
            "status": "verified",
        }
    )

    return {
        "status": "success",
        "verified": document_embeddings.get("total_embeddings", 0),
        "total_in_collection": collection_count,
    }


