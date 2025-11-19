"""Dagster definitions - entry point for the pipeline.

This module wires together all assets, resources, schedules, and sensors.
"""

import dagster as dg

from lovdata_pipeline.assets.chunking import legal_document_chunks
from lovdata_pipeline.assets.enrichment import enriched_chunks
from lovdata_pipeline.assets.ingestion import (
    changed_file_paths,
    lovdata_sync,
    removed_file_metadata,
)
from lovdata_pipeline.config.settings import get_settings
from lovdata_pipeline.resources.embedding import EmbeddingResource
from lovdata_pipeline.resources.lovlig import LovligResource

# Load settings from environment
settings = get_settings()

# Define schedule to run daily at 2 AM
daily_sync_schedule = dg.ScheduleDefinition(
    name="daily_lovdata_sync",
    target=[lovdata_sync, changed_file_paths, removed_file_metadata],
    cron_schedule="0 2 * * *",  # 2 AM daily
    execution_timezone="Europe/Oslo",
)

# Define Dagster resources
resources = {
    "lovlig": LovligResource(
        dataset_filter=settings.dataset_filter,
        raw_data_dir=str(settings.raw_data_dir),
        extracted_data_dir=str(settings.extracted_data_dir),
        state_file=str(settings.state_file),
        max_download_concurrency=settings.max_download_concurrency,
    ),
    "embedding": EmbeddingResource(
        model_name=settings.embedding_model,
        api_key=settings.openai_api_key,
        embedded_state_file=str(settings.embedded_files_state),
        lovlig_state_file=str(settings.state_file),
        batch_size=settings.embedding_batch_size,
    ),
}

# Define all assets
assets = [
    lovdata_sync,
    changed_file_paths,
    removed_file_metadata,
    legal_document_chunks,
    enriched_chunks,
]

# Create Dagster definitions
defs = dg.Definitions(
    assets=assets,
    resources=resources,
    schedules=[daily_sync_schedule],
)
