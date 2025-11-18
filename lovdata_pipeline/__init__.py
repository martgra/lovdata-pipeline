"""Lovdata Pipeline - Dagster pipeline for ingesting Norwegian legal documents.

This package provides a production-ready pipeline for:
- Syncing Lovdata legal documents using the lovlig library
- Parsing XML documents into structured chunks
- Generating embeddings with OpenAI
- Storing in ChromaDB vector database
- Observability with Langfuse
"""

__version__ = "0.1.0"

from lovdata_pipeline.definitions import defs

__all__ = ["defs"]
