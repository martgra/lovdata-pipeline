"""Dagster assets for the Lovdata pipeline."""

from lovdata_pipeline.assets.ingestion import (
    changed_legal_documents,
    lovdata_sync,
    parsed_legal_chunks,
)
from lovdata_pipeline.assets.loading import (
    cleanup_changed_documents,
    vector_database,
)
from lovdata_pipeline.assets.transformation import document_embeddings

__all__ = [
    "changed_legal_documents",
    "cleanup_changed_documents",
    "document_embeddings",
    "lovdata_sync",
    "parsed_legal_chunks",
    "vector_database",
]
