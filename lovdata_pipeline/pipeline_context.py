"""Pipeline context for dependency injection.

This module provides a centralized container for all pipeline dependencies,
following the dependency injection pattern for better testability and
separation of concerns.
"""

from dataclasses import dataclass

from openai import OpenAI

from lovdata_pipeline.config.settings import LovdataSettings, get_settings
from lovdata_pipeline.domain.splitters.recursive_splitter import XMLAwareRecursiveSplitter
from lovdata_pipeline.infrastructure.chroma_client import ChromaClient
from lovdata_pipeline.infrastructure.chunk_reader import ChunkReader, EnrichedChunkReader
from lovdata_pipeline.infrastructure.chunk_writer import ChunkWriter
from lovdata_pipeline.infrastructure.lovlig_client import LovligClient
from lovdata_pipeline.infrastructure.pipeline_manifest import PipelineManifest
from lovdata_pipeline.infrastructure.vector_db_client import VectorDBClient


@dataclass
class PipelineContext:
    """Container for all pipeline dependencies.

    This class follows the dependency injection pattern, allowing all
    dependencies to be created once and passed through the pipeline.
    This improves testability (easy to inject mocks) and reduces
    repetitive client instantiation throughout the codebase.

    Attributes:
        settings: Application settings loaded from environment
        lovlig_client: Client for Lovdata sync operations
        manifest: Unified pipeline manifest tracking all processing state
        chunk_writer: Writer for chunk JSONL output
        chunk_reader: Reader for chunk JSONL input
        splitter: XML-aware recursive splitter for chunking
        openai_client: OpenAI API client for embeddings
        chroma_client: Vector database client (ChromaDB or other implementation)
    """

    settings: LovdataSettings
    lovlig_client: LovligClient
    manifest: PipelineManifest
    chunk_writer: ChunkWriter
    chunk_reader: ChunkReader
    splitter: XMLAwareRecursiveSplitter
    openai_client: OpenAI
    chroma_client: VectorDBClient

    @classmethod
    def from_settings(cls, settings: LovdataSettings | None = None) -> "PipelineContext":
        """Create pipeline context from settings.

        Factory method that initializes all pipeline dependencies from
        application settings. This is the primary way to create a context.

        Args:
            settings: Optional settings; if None, loads from environment

        Returns:
            Fully initialized PipelineContext

        Example:
            >>> ctx = PipelineContext.from_settings()
            >>> stats = chunk_documents(ctx, changed_paths, removed_metadata)
        """
        if settings is None:
            settings = get_settings()

        # Initialize manifest first (needed by other clients)
        manifest = PipelineManifest(manifest_file=settings.pipeline_manifest_path)

        # Initialize all clients once
        lovlig_client = LovligClient(
            dataset_filter=settings.dataset_filter,
            raw_data_dir=settings.raw_data_dir,
            extracted_data_dir=settings.extracted_data_dir,
            state_file=settings.state_file,
            max_download_concurrency=settings.max_download_concurrency,
            manifest=manifest,  # Pass manifest for unified state tracking
        )

        chunk_writer = ChunkWriter(output_path=settings.chunk_output_path)

        chunk_reader = ChunkReader(chunks_file=settings.chunk_output_path)

        splitter = XMLAwareRecursiveSplitter(max_tokens=settings.chunk_max_tokens)

        openai_client = OpenAI(api_key=settings.openai_api_key)

        # Vector database client - currently only ChromaDB is supported
        if settings.vector_db_type != "chroma":
            raise ValueError(
                f"Unsupported vector_db_type: '{settings.vector_db_type}'. "
                f"Only 'chroma' is currently supported. "
                f"To add support for other databases, implement a VectorDBClient subclass."
            )

        vector_client = ChromaClient(
            mode=settings.chroma_mode,
            host=settings.chroma_host,
            port=settings.chroma_port,
            collection_name=settings.vector_db_collection,
            persist_directory=settings.chroma_persist_directory,
        )

        return cls(
            settings=settings,
            lovlig_client=lovlig_client,
            manifest=manifest,
            chunk_writer=chunk_writer,
            chunk_reader=chunk_reader,
            splitter=splitter,
            openai_client=openai_client,
            chroma_client=vector_client,
        )

    def get_enriched_chunk_reader(self) -> EnrichedChunkReader:
        """Get a chunk reader configured for enriched chunks.

        Returns:
            EnrichedChunkReader configured to read from enriched data directory
        """
        enriched_file = self.settings.enriched_data_dir / "embedded_chunks.jsonl"
        return EnrichedChunkReader(chunks_file=enriched_file)

    def get_enriched_chunk_writer(self) -> ChunkWriter:
        """Get a chunk writer configured for enriched chunks.

        Returns:
            ChunkWriter configured to write to enriched data directory
        """
        enriched_file = self.settings.enriched_data_dir / "embedded_chunks.jsonl"
        return ChunkWriter(output_path=enriched_file)
