"""Demo script showing end-to-end indexing with ChromaDB.

This script demonstrates:
1. Creating a ChromaDB client
2. Simulating document processing through pipeline stages
3. Tracking state with pipeline manifest
4. Indexing vectors to ChromaDB
5. Querying the index
6. Handling updates and deletions
"""

from pathlib import Path
from tempfile import TemporaryDirectory

from lovdata_pipeline.infrastructure.chroma_client import ChromaClient
from lovdata_pipeline.infrastructure.pipeline_manifest import (
    IndexStatus,
    PipelineManifest,
)


def main():
    """Run end-to-end indexing demo."""
    print("=" * 70)
    print("ChromaDB + Pipeline Manifest Demo")
    print("=" * 70)
    print()

    with TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Initialize components
        print("1. Initializing ChromaDB and Pipeline Manifest...")
        chroma_client = ChromaClient(
            persist_directory=str(tmp_path / "chroma"),
            collection_name="demo_legal_docs",
        )
        manifest = PipelineManifest(tmp_path / "manifest.json")
        print(f"   ✓ ChromaDB collection: {chroma_client.collection_name}")
        print(f"   ✓ Manifest file: {manifest.manifest_file}")
        print()

        # Add first document
        print("2. Processing first document (nl-18840614-003)...")
        doc1_id = "nl-18840614-003"
        doc1_hash = "abc123def456"  # pragma: allowlist secret

        manifest.ensure_document(
            document_id=doc1_id,
            dataset_name="gjeldende-lover",
            relative_path="nl/nl-18840614-003.xml",
            file_hash=doc1_hash,
            file_size_bytes=5000,
        )

        # Simulate chunking
        manifest.start_stage(doc1_id, doc1_hash, "chunking")
        manifest.complete_stage(doc1_id, doc1_hash, "chunking", output={"chunk_count": 3})
        print("   ✓ Chunking completed (3 chunks)")

        # Simulate embedding
        manifest.start_stage(doc1_id, doc1_hash, "embedding")
        manifest.complete_stage(doc1_id, doc1_hash, "embedding", output={"chunk_count": 3})
        print("   ✓ Embedding completed")

        # Index to ChromaDB
        manifest.start_stage(doc1_id, doc1_hash, "indexing")
        vector_ids = [f"{doc1_id}::{doc1_hash}::{i}" for i in range(3)]
        embeddings = [
            [0.1, 0.2, 0.3, 0.4],
            [0.5, 0.6, 0.7, 0.8],
            [0.9, 1.0, 1.1, 1.2],
        ]
        metadatas = [
            {
                "document_id": doc1_id,
                "chunk_index": i,
                "text": f"Article {i + 1} about Norwegian law",
            }
            for i in range(3)
        ]

        chroma_client.upsert(ids=vector_ids, embeddings=embeddings, metadatas=metadatas)
        manifest.complete_stage(doc1_id, doc1_hash, "indexing", output={"vector_ids": vector_ids})
        manifest.set_index_status(doc1_id, IndexStatus.INDEXED)
        print("   ✓ Indexed 3 vectors to ChromaDB")
        print(f"   ✓ Total vectors in collection: {chroma_client.count()}")
        print()

        # Add second document
        print("3. Processing second document (nl-18880623-003)...")
        doc2_id = "nl-18880623-003"
        doc2_hash = "xyz789abc123"

        manifest.ensure_document(
            document_id=doc2_id,
            dataset_name="gjeldende-lover",
            relative_path="nl/nl-18880623-003.xml",
            file_hash=doc2_hash,
            file_size_bytes=3500,
        )

        # Process and index
        manifest.start_stage(doc2_id, doc2_hash, "chunking")
        manifest.complete_stage(doc2_id, doc2_hash, "chunking", output={"chunk_count": 2})
        manifest.start_stage(doc2_id, doc2_hash, "embedding")
        manifest.complete_stage(doc2_id, doc2_hash, "embedding", output={"chunk_count": 2})
        manifest.start_stage(doc2_id, doc2_hash, "indexing")

        vector_ids_2 = [f"{doc2_id}::{doc2_hash}::{i}" for i in range(2)]
        embeddings_2 = [[0.2, 0.3, 0.4, 0.5], [0.6, 0.7, 0.8, 0.9]]
        metadatas_2 = [
            {"document_id": doc2_id, "chunk_index": i, "text": f"Section {i + 1} on regulations"}
            for i in range(2)
        ]

        chroma_client.upsert(ids=vector_ids_2, embeddings=embeddings_2, metadatas=metadatas_2)
        manifest.complete_stage(doc2_id, doc2_hash, "indexing", output={"vector_ids": vector_ids_2})
        manifest.set_index_status(doc2_id, IndexStatus.INDEXED)
        print("   ✓ Indexed 2 vectors to ChromaDB")
        print(f"   ✓ Total vectors in collection: {chroma_client.count()}")
        print()

        # Query the index
        print("4. Querying the index...")
        query_embedding = [0.15, 0.25, 0.35, 0.45]
        results = chroma_client.query(query_embeddings=[query_embedding], n_results=3)

        print("   Query: embedding close to document 1, chunk 0")
        print("   Top 3 results:")
        for i, (doc_id, metadata) in enumerate(
            zip(results["ids"][0], results["metadatas"][0], strict=False), 1
        ):
            print(f"     {i}. {doc_id}")
            print(f"        Text: {metadata.get('text', 'N/A')}")
        print()

        # Handle document update
        print("5. Simulating document update (nl-18840614-003 modified)...")
        doc1_hash_v2 = "new_hash_v2"

        # Delete old vectors
        deleted_count = chroma_client.delete_by_metadata(where={"document_id": doc1_id})
        print(f"   ✓ Deleted {deleted_count} old vectors")

        # Update manifest (new version)
        manifest.ensure_document(
            document_id=doc1_id,
            dataset_name="gjeldende-lover",
            relative_path="nl/nl-18840614-003.xml",
            file_hash=doc1_hash_v2,
            file_size_bytes=5500,
        )

        # Index new version (now 4 chunks)
        manifest.start_stage(doc1_id, doc1_hash_v2, "chunking")
        manifest.complete_stage(doc1_id, doc1_hash_v2, "chunking", output={"chunk_count": 4})
        manifest.start_stage(doc1_id, doc1_hash_v2, "embedding")
        manifest.complete_stage(doc1_id, doc1_hash_v2, "embedding", output={"chunk_count": 4})
        manifest.start_stage(doc1_id, doc1_hash_v2, "indexing")

        vector_ids_new = [f"{doc1_id}::{doc1_hash_v2}::{i}" for i in range(4)]
        embeddings_new = [
            [0.11, 0.21, 0.31, 0.41],
            [0.51, 0.61, 0.71, 0.81],
            [0.91, 1.01, 1.11, 1.21],
            [1.31, 1.41, 1.51, 1.61],
        ]
        metadatas_new = [
            {
                "document_id": doc1_id,
                "chunk_index": i,
                "text": f"Updated Article {i + 1}",
            }
            for i in range(4)
        ]

        chroma_client.upsert(ids=vector_ids_new, embeddings=embeddings_new, metadatas=metadatas_new)
        manifest.complete_stage(
            doc1_id, doc1_hash_v2, "indexing", output={"vector_ids": vector_ids_new}
        )
        manifest.set_index_status(doc1_id, IndexStatus.INDEXED)
        print("   ✓ Indexed 4 new vectors (updated content)")
        print(f"   ✓ Total vectors in collection: {chroma_client.count()}")
        print()

        # Handle document deletion
        print("6. Simulating document deletion (nl-18880623-003 removed)...")
        deleted_count = chroma_client.delete_by_metadata(where={"document_id": doc2_id})
        manifest.set_index_status(doc2_id, IndexStatus.DELETED)
        print(f"   ✓ Deleted {deleted_count} vectors")
        print(f"   ✓ Total vectors in collection: {chroma_client.count()}")
        print()

        # Show manifest summary
        print("7. Pipeline Manifest Summary...")
        manifest.save()

        indexed_docs = manifest.get_documents_by_index_status(IndexStatus.INDEXED)
        deleted_docs = manifest.get_documents_by_index_status(IndexStatus.DELETED)

        print(f"   ✓ Documents indexed: {len(indexed_docs)}")
        for doc in indexed_docs:
            print(f"     - {doc.document_id} (hash: {doc.current_version.file_hash[:8]}...)")
            if doc.version_history:
                print(
                    f"       Previous versions: {len(doc.version_history)} "
                    f"(hashes: {', '.join(v.file_hash[:8] for v in doc.version_history)})"
                )

        print(f"   ✓ Documents deleted: {len(deleted_docs)}")
        for doc in deleted_docs:
            print(f"     - {doc.document_id}")
        print()

        # Show collection info
        print("8. ChromaDB Collection Info...")
        info = chroma_client.get_collection_info()
        print(f"   ✓ Collection name: {info['name']}")
        print(f"   ✓ Total vectors: {info['count']}")
        print(f"   ✓ Metadata: {info['metadata']}")
        print()

        print("=" * 70)
        print("Demo completed successfully!")
        print("=" * 70)
        print()
        print("Summary:")
        print("✓ ChromaDB client integration working")
        print("✓ Pipeline manifest tracking all stages")
        print("✓ Vector indexing and querying functional")
        print("✓ Document updates handled correctly")
        print("✓ Document deletions working as expected")
        print("✓ Version history maintained in manifest")
        print()


if __name__ == "__main__":
    main()
