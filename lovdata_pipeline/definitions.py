"""Dagster definitions for the Lovdata pipeline.

This module assembles all assets, resources, schedules, and sensors
for the complete pipeline.
"""

from __future__ import annotations

import os

from dagster import (
    AssetSelection,
    DefaultScheduleStatus,
    Definitions,
    EnvVar,
    ScheduleDefinition,
    define_asset_job,
    in_process_executor,
)
from dagster_openai import OpenAIResource

from lovdata_pipeline.assets import (
    changed_legal_documents,
    cleanup_changed_documents,
    document_embeddings,
    lovdata_sync,
    parsed_legal_chunks,
    vector_database,
)
from lovdata_pipeline.io_managers import ChunksIOManager
from lovdata_pipeline.resources import ChromaDBResource, LovligResource

# ============================================================================
# JOBS
# ============================================================================

# Main processing job that runs all assets
lovdata_processing_job = define_asset_job(
    name="lovdata_processing_job",
    selection=AssetSelection.all(),
    description="Complete pipeline for processing Lovdata legal documents",
    executor_def=in_process_executor,  # Use in-process to avoid SIGBUS with large data
)

# Sync-only job for testing/debugging
lovdata_sync_only_job = define_asset_job(
    name="lovdata_sync_only_job",
    selection=AssetSelection.assets(lovdata_sync),
    description="Only sync Lovdata datasets without processing",
    executor_def=in_process_executor,
)


# ============================================================================
# SCHEDULES
# ============================================================================

daily_lovdata_schedule = ScheduleDefinition(
    name="daily_lovdata_schedule",
    job=lovdata_processing_job,
    cron_schedule="0 2 * * *",  # Daily at 2 AM
    default_status=DefaultScheduleStatus.STOPPED,
    description="Daily schedule for processing Lovdata documents",
)


# ============================================================================
# RESOURCES CONFIGURATION
# ============================================================================

deployment = os.getenv("DAGSTER_DEPLOYMENT", "local")

resources_by_env = {
    "local": {
        "lovlig": LovligResource(
            dataset_filter="gjeldende",
            raw_data_dir="./data/raw",
            extracted_data_dir="./data/extracted",
            state_file="./data/state.json",
            max_download_concurrency=4,
        ),
        "openai": OpenAIResource(api_key=EnvVar("OPENAI_API_KEY")),
        "chromadb": ChromaDBResource(
            persist_directory="./data/chromadb",
            collection_name="lovdata_legal_docs",
            distance_metric="cosine",
        ),
        "chunks_io_manager": ChunksIOManager(base_dir="./data/io_manager"),
    },
    "production": {
        "lovlig": LovligResource(
            dataset_filter=EnvVar("LOVDATA_DATASET_FILTER"),
            raw_data_dir=EnvVar("LOVDATA_RAW_DIR"),
            extracted_data_dir=EnvVar("LOVDATA_EXTRACTED_DIR"),
            state_file=EnvVar("LOVDATA_STATE_FILE"),
            max_download_concurrency=EnvVar.int("LOVDATA_MAX_CONCURRENCY"),
        ),
        "openai": OpenAIResource(api_key=EnvVar("OPENAI_API_KEY_PROD")),
        "chromadb": ChromaDBResource(
            persist_directory=EnvVar("CHROMADB_PERSIST_DIR"),
            collection_name=EnvVar("CHROMADB_COLLECTION_NAME"),
            distance_metric=EnvVar("CHROMADB_DISTANCE_METRIC"),
        ),
        "chunks_io_manager": ChunksIOManager(base_dir=EnvVar("IO_MANAGER_BASE_DIR")),
    },
}


# ============================================================================
# DEFINITIONS
# ============================================================================

defs = Definitions(
    assets=[
        lovdata_sync,
        changed_legal_documents,
        parsed_legal_chunks,
        cleanup_changed_documents,
        document_embeddings,
        vector_database,
    ],
    jobs=[lovdata_processing_job, lovdata_sync_only_job],
    schedules=[daily_lovdata_schedule],
    resources=resources_by_env[deployment],
)
