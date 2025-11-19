"""Quick example of using ChromaDB client with pipeline manifest.

This shows the basic pattern for indexing documents.
"""

from lovdata_pipeline.infrastructure.chroma_client import ChromaClient
from lovdata_pipeline.infrastructure.pipeline_manifest import (
    ErrorClassification,
    IndexStatus,
    PipelineManifest,
)

# Initialize
chroma = ChromaClient(persist_directory="./data/chroma", collection_name="legal_docs")
manifest = PipelineManifest.load()

# Process a document
doc_id = "nl-18840614-003"
file_hash = "abc123"

# Ensure document exists in manifest
manifest.ensure_document(
    document_id=doc_id,
    dataset_name="gjeldende-lover",
    relative_path="nl/nl-18840614-003.xml",
    file_hash=file_hash,
    file_size_bytes=5000,
)

# Complete previous stages (chunking, embedding)
# ... (see other assets)

# Start indexing stage
manifest.start_stage(doc_id, file_hash, "indexing")

try:
    # Read enriched chunks (with embeddings)
    # In real code, read from embedded_chunks.jsonl
    vector_ids = [f"{doc_id}::{file_hash}::{i}" for i in range(3)]
    embeddings = [[0.1, 0.2, 0.3]] * 3  # Real embeddings from OpenAI
    metadatas = [{"document_id": doc_id, "chunk_index": i} for i in range(3)]

    # Index to ChromaDB
    chroma.upsert(ids=vector_ids, embeddings=embeddings, metadatas=metadatas)

    # Mark as complete
    manifest.complete_stage(doc_id, file_hash, "indexing", output={"vector_ids": vector_ids})
    manifest.set_index_status(doc_id, IndexStatus.INDEXED)

except Exception as e:
    # Handle failure
    manifest.fail_stage(
        doc_id,
        file_hash,
        "indexing",
        error_type=type(e).__name__,
        error_message=str(e),
        classification=ErrorClassification.TRANSIENT,
    )

# Save manifest
manifest.save()

# Query the index
query_embedding = [0.15, 0.25, 0.35]
results = chroma.query(query_embeddings=[query_embedding], n_results=5)

print(f"Found {len(results['ids'][0])} similar chunks")
for doc_id, metadata in zip(results["ids"][0], results["metadatas"][0], strict=False):
    print(f"  - {doc_id}: {metadata}")
