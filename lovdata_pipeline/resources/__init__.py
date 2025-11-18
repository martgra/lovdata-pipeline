"""Dagster resources for external services."""

from lovdata_pipeline.resources.chromadb_resource import ChromaDBResource
from lovdata_pipeline.resources.lovlig_resource import LovligResource

__all__ = ["ChromaDBResource", "LovligResource"]
