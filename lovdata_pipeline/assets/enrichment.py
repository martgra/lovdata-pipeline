"""Enrichment assets for adding embeddings to legal document chunks.

These assets orchestrate the embedding pipeline to:
1. Identify which files need embedding
2. Read chunks from legal_chunks.jsonl
3. Generate embeddings using OpenAI API
4. Write enriched chunks to embedded_chunks.jsonl
"""

from pathlib import Path

import dagster as dg

from lovdata_pipeline.config.settings import get_settings
from lovdata_pipeline.infrastructure.chunk_reader import ChunkReader
from lovdata_pipeline.infrastructure.enriched_writer import EnrichedChunkWriter
from lovdata_pipeline.resources.embedding import EmbeddingResource


@dg.asset(
    group_name="enrichment",
    compute_kind="embedding",
    deps=["legal_document_chunks"],
    description="Enrich chunks with embeddings for changed/added files",
)
def enriched_chunks(
    context: dg.AssetExecutionContext,
    changed_file_paths: list[str],
    removed_file_metadata: list[dict],
    embedding: EmbeddingResource,
) -> dg.MaterializeResult:
    """Enrich chunks with embeddings for changed/added files.

    This asset:
    1. Removes embeddings for deleted files
    2. Removes embeddings for modified files
    3. Reads chunks from legal_chunks.jsonl by document
    4. Embeds chunks in batches using OpenAI API
    5. Streams enriched chunks to enriched/embedded_chunks.jsonl
    6. Marks files as embedded

    Incremental behavior:
    - Skips files that haven't changed since last embedding
    - Re-embeds entire document if file hash changed
    - Automatically cleans up deleted files

    Args:
        context: Dagster execution context
        changed_file_paths: List of XML file paths that changed
        removed_file_metadata: Metadata about deleted files
        embedding: Embedding resource for model access

    Returns:
        MaterializeResult with embedding statistics
    """
    settings = get_settings()

    # Filter to files needing embedding
    files_to_embed = embedding.get_files_needing_embedding(
        changed_file_paths, force_reembed=settings.force_reembed
    )

    if not files_to_embed and not removed_file_metadata:
        context.log.info("No files need embedding")
        return dg.MaterializeResult(
            metadata={
                "files_embedded": 0,
                "chunks_embedded": 0,
                "files_deleted": 0,
                "output_file": str(settings.enriched_data_dir / "embedded_chunks.jsonl"),
                "model_name": settings.embedding_model,
            }
        )

    context.log.info(f"Embedding {len(files_to_embed)} files")
    context.log.info(f"Model: {settings.embedding_model}")
    context.log.info(f"Batch size: {settings.embedding_batch_size}")

    # Output setup
    output_file = settings.enriched_data_dir / "embedded_chunks.jsonl"
    output_file.parent.mkdir(parents=True, exist_ok=True)

    writer = EnrichedChunkWriter(output_file)
    chunk_reader = ChunkReader(settings.chunk_output_path)

    # Statistics
    total_chunks_embedded = 0
    total_files_embedded = 0
    files_failed = 0
    chunks_removed_deleted = 0

    # PASS 1A: Remove embeddings for deleted files
    for removal in removed_file_metadata:
        doc_id = removal["document_id"]
        removed = writer.remove_chunks_for_document(doc_id)
        if removed > 0:
            context.log.info(f"Removed {removed} embeddings for deleted file {doc_id}")
            chunks_removed_deleted += removed

    # PASS 1B: Remove old embeddings for files being re-embedded
    for file_meta in files_to_embed:
        doc_id = file_meta.document_id
        removed = writer.remove_chunks_for_document(doc_id)
        if removed > 0:
            context.log.info(f"Removed {removed} old embeddings for {doc_id}")

    # PASS 2: Read chunks, embed, and write
    with writer:
        for file_meta in files_to_embed:
            doc_id = file_meta.document_id

            try:
                # Read all chunks for this document
                chunks = chunk_reader.read_chunks_for_document(doc_id)

                if not chunks:
                    context.log.warning(f"No chunks found for {doc_id}")
                    continue

                context.log.info(f"Embedding {len(chunks)} chunks for {doc_id}")

                # Extract text content
                chunk_texts = [c["content"] for c in chunks]

                # Embed in batches
                embeddings = []
                for i in range(0, len(chunk_texts), settings.embedding_batch_size):
                    batch = chunk_texts[i : i + settings.embedding_batch_size]
                    batch_embeddings = embedding.embed_batch(batch)
                    embeddings.extend(batch_embeddings)

                    context.log.debug(
                        f"Embedded batch {i // settings.embedding_batch_size + 1} "
                        f"({len(batch)} chunks)"
                    )

                # Write enriched chunks
                for chunk, emb in zip(chunks, embeddings, strict=False):
                    enriched = {
                        **chunk,
                        "embedding": emb,
                        "embedding_model": settings.embedding_model,
                    }
                    writer.write_chunk(enriched)

                total_chunks_embedded += len(chunks)
                total_files_embedded += 1

                # Extract dataset info and file hash for marking as embedded
                try:
                    # Parse file path to get dataset and relative path
                    file_path_obj = Path(str(file_meta.absolute_path))
                    parts = file_path_obj.parts

                    # Find "extracted" directory
                    extracted_idx = None
                    for idx, part in enumerate(parts):
                        if part == "extracted":
                            extracted_idx = idx
                            break

                    if extracted_idx and extracted_idx + 1 < len(parts):
                        dataset_name_raw = parts[extracted_idx + 1]
                        dataset_name = f"{dataset_name_raw}.tar.bz2"
                        relative_path = str(Path(*parts[extracted_idx + 2 :]))

                        # Get file hash from lovlig state
                        # We'll need to read it from the embedded client
                        # For now, use a placeholder - the client will look it up
                        file_hash = "embedded"  # Client will get actual hash

                        # Mark as embedded
                        embedding.mark_file_embedded(
                            dataset_name=dataset_name,
                            file_path=relative_path,
                            file_hash=file_hash,
                            chunk_count=len(chunks),
                        )
                        context.log.debug(f"Marked {doc_id} as embedded")
                except Exception as e:
                    context.log.warning(
                        f"Could not mark {doc_id} as embedded: {e}. "
                        "File will be re-embedded on next run."
                    )

            except Exception as e:
                context.log.error(f"Failed to embed {doc_id}: {e}")
                files_failed += 1
                continue

    # Get output file size
    output_size_mb = writer.get_file_size_mb()

    # Calculate statistics
    success_rate = (total_files_embedded / len(files_to_embed) * 100) if files_to_embed else 100.0

    context.log.info(f"✓ Embedded {total_files_embedded} files successfully")
    context.log.info(f"✓ Generated {total_chunks_embedded} embeddings")
    context.log.info(f"✓ Output size: {output_size_mb:.2f} MB")

    if files_failed > 0:
        context.log.warning(f"⚠ {files_failed} files failed to embed")

    # Return metadata
    return dg.MaterializeResult(
        metadata={
            "files_embedded": dg.MetadataValue.int(total_files_embedded),
            "files_failed": dg.MetadataValue.int(files_failed),
            "files_deleted": dg.MetadataValue.int(len(removed_file_metadata)),
            "chunks_removed_for_deleted": dg.MetadataValue.int(chunks_removed_deleted),
            "chunks_embedded": dg.MetadataValue.int(total_chunks_embedded),
            "output_file": dg.MetadataValue.path(str(output_file)),
            "output_size_mb": dg.MetadataValue.float(round(output_size_mb, 2)),
            "model_name": dg.MetadataValue.text(settings.embedding_model),
            "success_rate": dg.MetadataValue.float(round(success_rate, 2)),
        }
    )
