"""Atomic per-file pipeline: read → parse → embed → index.

Each file goes through the complete pipeline before moving to the next.
No intermediate state, no complex recovery - just process files.
"""

import logging
from pathlib import Path

import chromadb
from lxml import etree as ET
from openai import OpenAI

from lovdata_pipeline.domain.models import ChunkMetadata, EnrichedChunk
from lovdata_pipeline.domain.splitters.recursive_splitter import XMLAwareRecursiveSplitter
from lovdata_pipeline.progress import ProgressTracker, NoOpProgressTracker

logger = logging.getLogger(__name__)


def extract_articles_from_xml(xml_path: Path) -> list[dict]:
    """Parse XML and extract articles.

    Returns list of dicts with:
        - id: article ID
        - content: full text
        - heading: section heading
        - address: lovdata URL
    """
    tree = ET.parse(str(xml_path))
    root = tree.getroot()
    articles = []

    for elem in root.xpath('//article[@class="legalArticle"]'):
        article_id = elem.get("id") or elem.get("data-name", "unknown")
        address = elem.get("data-lovdata-URL", "")

        # Get heading
        heading = ""
        for h_tag in ["h2", "h3", "h4"]:
            h = elem.find(f'.//{h_tag}[@class="legalArticleHeader"]')
            if h is not None and h.text:
                heading = h.text.strip()
                break

        # Get all text
        content = "".join(elem.itertext()).strip()

        if content:
            articles.append(
                {
                    "id": article_id,
                    "content": content,
                    "heading": heading,
                    "address": address,
                }
            )

    return articles


def chunk_article(article: dict, doc_id: str, dataset: str, max_tokens: int) -> list[ChunkMetadata]:
    """Split article into chunks if needed."""
    from lovdata_pipeline.domain.parsers.xml_chunker import LegalArticle

    # Convert to LegalArticle format
    legal_article = LegalArticle(
        article_id=article["id"],
        content=article["content"],
        paragraphs=[],  # We extract text directly, not parsing paragraphs
        section_heading=article["heading"],
        absolute_address=article["address"],
        document_id=doc_id,
    )

    # Split if needed
    splitter = XMLAwareRecursiveSplitter(max_tokens=max_tokens)
    chunks = splitter.split_article(legal_article, dataset_name=dataset)

    return chunks


def embed_chunks(
    chunks: list[ChunkMetadata],
    openai_client: OpenAI,
    model: str,
    progress_tracker: ProgressTracker,
) -> list[EnrichedChunk]:
    """Embed chunks in batches of 100."""
    from datetime import UTC, datetime

    all_enriched = []
    batch_size = 100
    total_chunks = len(chunks)

    # Start tracking embedding progress
    progress_tracker.start_embedding(total_chunks)

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        texts = [c.text for c in batch]

        response = openai_client.embeddings.create(input=texts, model=model)
        embeddings = [item.embedding for item in response.data]

        # Create enriched chunks
        embedded_at = datetime.now(UTC).isoformat()
        for chunk, embedding in zip(batch, embeddings, strict=True):
            enriched = EnrichedChunk(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                dataset_name=chunk.dataset_name,
                content=chunk.content,
                token_count=chunk.token_count,
                section_heading=chunk.section_heading,
                absolute_address=chunk.absolute_address,
                split_reason=chunk.split_reason,
                parent_chunk_id=chunk.parent_chunk_id,
                embedding=embedding,
                embedding_model=model,
                embedded_at=embedded_at,
            )
            all_enriched.append(enriched)

        # Update progress after each batch
        progress_tracker.update_embedding(len(all_enriched), total_chunks)

    # End embedding progress
    progress_tracker.end_embedding()

    return all_enriched


def process_file(
    file_info: dict,
    chroma_collection,
    openai_client: OpenAI,
    config: dict,
    progress_tracker: ProgressTracker,
) -> tuple[bool, int, str | None]:
    """Process one file atomically.

    Returns:
        (success, chunk_count, error_message)
    """
    doc_id = file_info["doc_id"]
    xml_path = file_info["path"]

    vector_ids_to_cleanup = []

    try:
        # Validate file exists
        if not xml_path.exists():
            return False, 0, f"File not found: {xml_path}"

        # 1. Parse XML
        articles = extract_articles_from_xml(xml_path)
        if not articles:
            progress_tracker.log_warning(f"No articles in {doc_id}")
            return True, 0, None

        # 2. Chunk articles
        all_chunks = []
        for article in articles:
            chunks = chunk_article(
                article,
                doc_id,
                file_info["dataset"],
                config["chunk_max_tokens"],
            )
            all_chunks.extend(chunks)

        if not all_chunks:
            return True, 0, None

        logger.debug(f"  Chunked: {len(all_chunks)} chunks")

        # 3. Embed (with progress tracking)
        enriched = embed_chunks(
            all_chunks, openai_client, config["embedding_model"], progress_tracker
        )
        logger.debug(f"  Embedded: {len(enriched)} chunks")

        # 4. Generate vector IDs
        vector_ids = [f"{doc_id}_chunk_{i}" for i in range(len(enriched))]
        vector_ids_to_cleanup = vector_ids  # Track for cleanup on failure

        # Set IDs on enriched chunks
        for chunk, vid in zip(enriched, vector_ids, strict=True):
            chunk.chunk_id = vid

        # 5. Index in ChromaDB (upsert = replace old if exists)
        chroma_collection.upsert(
            ids=vector_ids,
            embeddings=[c.embedding for c in enriched],
            metadatas=[c.metadata for c in enriched],
            documents=[c.text for c in enriched],
        )

        logger.debug(f"  Indexed: {len(vector_ids)} vectors")

        return True, len(all_chunks), None

    except Exception as e:
        logger.debug(f"  Failed: {e}")

        # Clean up any partial vectors that may have been indexed
        if vector_ids_to_cleanup:
            try:
                chroma_collection.delete(ids=vector_ids_to_cleanup)
                logger.debug(f"  Cleaned up {len(vector_ids_to_cleanup)} partial vectors")
            except Exception as cleanup_error:
                logger.debug(f"  Failed to clean up partial vectors: {cleanup_error}")

        return False, 0, str(e)


def run_pipeline(config: dict, progress_tracker: ProgressTracker | None = None):
    """Run complete pipeline.

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
    """
    from lovdata_pipeline.lovlig import Lovlig
    from lovdata_pipeline.state import ProcessingState

    # Use NoOp tracker if none provided (maintains backward compatibility)
    if progress_tracker is None:
        progress_tracker = NoOpProgressTracker()

    data_dir = Path(config["data_dir"])

    # Initialize
    lovlig = Lovlig(
        dataset_filter=config["dataset_filter"],
        raw_dir=data_dir / "raw",
        extracted_dir=data_dir / "extracted",
        state_file=data_dir / "state.json",
    )

    state = ProcessingState(data_dir / "pipeline_state.json")
    openai_client = OpenAI(api_key=config["openai_api_key"])

    # ChromaDB
    chroma_client = chromadb.PersistentClient(path=config["chroma_path"])
    collection = chroma_client.get_or_create_collection(
        name="legal_docs",
        metadata={"description": "Norwegian legal documents"},
    )

    # Validate ChromaDB is working
    try:
        collection.count()
    except Exception as e:
        raise RuntimeError(f"ChromaDB connection failed: {e}") from e

    # Step 1: Sync
    progress_tracker.start_stage("sync", "Syncing datasets")
    stats = lovlig.sync(force=config.get("force", False))
    logger.debug(
        f"Sync stats - Added: {stats['added']}, Modified: {stats['modified']}, Removed: {stats['removed']}"
    )
    progress_tracker.end_stage("sync")

    # Validate lovlig state was created
    if not lovlig.state_file.exists():
        raise RuntimeError(
            f"Lovlig state file not created at {lovlig.state_file}. "
            "Sync may have failed. Check network connection and permissions."
        )

    # Step 2: Get files to process
    progress_tracker.start_stage("identify", "Identifying files")
    changed = lovlig.get_changed_files()
    removed = lovlig.get_removed_files()

    # Filter already processed (unless force)
    to_process = []
    if config.get("force"):
        to_process = changed
    else:
        for f in changed:
            if not state.is_processed(f["doc_id"], f["hash"]):
                to_process.append(f)

    logger.debug(f"Processing {len(to_process)} files, skipped {len(changed) - len(to_process)}")
    progress_tracker.end_stage("identify")

    # Step 3: Process each file
    progress_tracker.start_stage("process", "Processing documents")
    processed = 0
    failed = 0

    # Start file processing progress bar
    if to_process:
        progress_tracker.start_file_processing(len(to_process))

        for idx, file_info in enumerate(to_process, 1):
            doc_id = file_info["doc_id"]

            # Update progress bar with current file
            progress_tracker.update_file(doc_id, idx - 1, len(to_process))

            success, chunk_count, error = process_file(
                file_info, collection, openai_client, config, progress_tracker
            )

            if success:
                # Generate vector IDs for state tracking
                vector_ids = [f"{doc_id}_chunk_{i}" for i in range(chunk_count)]
                state.mark_processed(doc_id, file_info["hash"], vector_ids)
                state.save()
                processed += 1
                progress_tracker.log_success(doc_id, chunk_count)
            else:
                state.mark_failed(doc_id, file_info["hash"], error or "Unknown error")
                state.save()
                failed += 1
                progress_tracker.log_error(doc_id, error or "Unknown error")

        # Complete the progress bar
        progress_tracker.update_file("", len(to_process), len(to_process))
        progress_tracker.end_file_processing()

    progress_tracker.end_stage("process")

    # Step 4: Clean up removed files
    if removed:
        progress_tracker.start_stage("cleanup", "Cleaning up removed documents")
        removed_count = 0
        for r in removed:
            doc_id = r["doc_id"]
            vectors = state.get_vectors(doc_id)
            if vectors:
                collection.delete(ids=vectors)
                logger.debug(f"Deleted {len(vectors)} vectors for {doc_id}")
                removed_count += 1
            else:
                progress_tracker.log_warning(
                    f"Document {doc_id} removed but not in state. "
                    "Ghost vectors may remain in ChromaDB."
                )
            state.remove(doc_id)
        state.save()
        progress_tracker.end_stage("cleanup")

    # Summary
    summary = state.stats()
    summary["removed"] = len(removed) if removed else 0
    progress_tracker.show_summary(summary)

    return {"processed": processed, "failed": failed}
