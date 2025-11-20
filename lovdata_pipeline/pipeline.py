"""Pipeline factory and entry point.

Creates and configures the pipeline orchestrator with all required services.
This module now has a single responsibility: wiring up dependencies.
"""

import logging

import chromadb
from openai import OpenAI

from lovdata_pipeline.config.settings import PipelineSettings
from lovdata_pipeline.domain.services.chunking_service import ChunkingService
from lovdata_pipeline.domain.services.embedding_service import EmbeddingService
from lovdata_pipeline.domain.services.file_processing_service import FileProcessingService
from lovdata_pipeline.infrastructure.chroma_vector_store import ChromaVectorStoreRepository
from lovdata_pipeline.infrastructure.openai_embedding_provider import (
    OpenAIEmbeddingProvider,
)
from lovdata_pipeline.orchestration.pipeline_orchestrator import (
    PipelineConfig,
    PipelineOrchestrator,
)
from lovdata_pipeline.progress import NoOpProgressTracker, ProgressTracker

logger = logging.getLogger(__name__)


def create_pipeline_orchestrator(
    openai_api_key: str,
    embedding_model: str,
    chunk_max_tokens: int,
    chroma_path: str,
    storage_type: str = "chroma",
    data_dir: str = "./data",
    chunk_target_tokens: int = 512,
    chunk_overlap_ratio: float = 0.15,
) -> PipelineOrchestrator:
    """Factory function to create a fully configured pipeline orchestrator.

    Single Responsibility: Dependency injection and wiring.

    Args:
        openai_api_key: OpenAI API key
        embedding_model: Model to use for embeddings
        chunk_max_tokens: Maximum tokens per chunk
        chroma_path: Path to ChromaDB storage
        storage_type: Storage type ('chroma' or 'jsonl')
        data_dir: Data directory for JSONL storage
        chunk_target_tokens: Target tokens per chunk (default: 512)
        chunk_overlap_ratio: Overlap ratio between chunks (default: 0.15)

    Returns:
        Configured PipelineOrchestrator instance
    """
    # Create infrastructure dependencies
    openai_client = OpenAI(api_key=openai_api_key)
    embedding_provider = OpenAIEmbeddingProvider(openai_client, embedding_model)

    # Initialize vector store based on storage type
    if storage_type == "jsonl":
        from pathlib import Path

        from lovdata_pipeline.infrastructure.jsonl_vector_store import JsonlVectorStoreRepository

        jsonl_path = Path(data_dir) / "jsonl_chunks"
        vector_store = JsonlVectorStoreRepository(jsonl_path)
        logger.info(f"Using JSONL storage at: {jsonl_path}")
    else:  # chroma (default)
        chroma_client = chromadb.PersistentClient(path=chroma_path)
        collection = chroma_client.get_or_create_collection(
            name="legal_docs",
            metadata={"description": "Norwegian legal documents"},
        )
        vector_store = ChromaVectorStoreRepository(collection)
        logger.info(f"Using ChromaDB storage at: {chroma_path}")

    # Create domain services
    chunking_service = ChunkingService(
        target_tokens=chunk_target_tokens,
        max_tokens=chunk_max_tokens,
        overlap_ratio=chunk_overlap_ratio,
    )
    embedding_service = EmbeddingService(provider=embedding_provider, batch_size=100)

    # Create file processing service
    file_processor = FileProcessingService(
        chunking_service=chunking_service,
        embedding_service=embedding_service,
        vector_store=vector_store,
    )

    # Create and return orchestrator
    return PipelineOrchestrator(
        file_processor=file_processor,
        vector_store=vector_store,
    )


def run_pipeline(config: PipelineSettings, progress_tracker: ProgressTracker | None = None):
    """Run complete pipeline (backward compatibility wrapper).

    This function maintains backward compatibility with existing code.
    It creates the orchestrator and runs the pipeline.

    Config should have:
        - data_dir: Path
        - dataset_filter: str
        - chunk_max_tokens: int
        - embedding_model: str
        - openai_api_key: str
        - chroma_path: str
        - force: bool (optional)

    Args:
        config: Pipeline configuration dictionary
        progress_tracker: Optional progress tracker. If None, uses NoOpProgressTracker.

    Returns:
        Dictionary with 'processed' and 'failed' counts
    """
    # Create orchestrator with dependencies
    orchestrator = create_pipeline_orchestrator(
        openai_api_key=config.openai_api_key,
        embedding_model=config.embedding_model,
        chunk_max_tokens=config.chunk_max_tokens,
        chroma_path=str(config.chroma_path),
        storage_type=config.storage_type,
        data_dir=str(config.data_dir),
    )

    # Create pipeline config
    pipeline_config = PipelineConfig(
        data_dir=config.data_dir,
        dataset_filter=config.dataset_filter,
        force=config.force or False,
        limit=config.limit,
    )

    # Use NoOp tracker if none provided
    if progress_tracker is None:
        progress_tracker = NoOpProgressTracker()

    # Run pipeline
    result = orchestrator.run(pipeline_config, progress_tracker)

    # Return in expected format for backward compatibility
    return {"processed": result.processed, "failed": result.failed}
