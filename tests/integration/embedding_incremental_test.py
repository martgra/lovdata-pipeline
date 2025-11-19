"""Integration tests for incremental embedding updates.

Tests the complete embedding pipeline behavior when datasets are updated with:
- Added files
- Modified files
- Removed files
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import pytest

from lovdata_pipeline.domain.models import ChunkMetadata
from lovdata_pipeline.infrastructure.chunk_reader import ChunkReader
from lovdata_pipeline.infrastructure.chunk_writer import ChunkWriter
from lovdata_pipeline.infrastructure.embedded_file_client import EmbeddedFileClient
from lovdata_pipeline.infrastructure.enriched_writer import EnrichedChunkWriter


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace with all necessary directories."""
    with TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)

        # Create directory structure
        (workspace / "data" / "raw").mkdir(parents=True)
        (workspace / "data" / "extracted" / "gjeldende-lover" / "nl").mkdir(parents=True)
        (workspace / "data" / "chunks").mkdir(parents=True)
        (workspace / "data" / "enriched").mkdir(parents=True)

        yield workspace


def create_sample_chunks(doc_id: str, content_version: str, num_chunks: int = 2) -> list[dict]:
    """Create sample chunks for testing."""
    chunks = []
    for i in range(num_chunks):
        chunk = ChunkMetadata(
            chunk_id=f"{doc_id}_chunk{i}",
            document_id=doc_id,
            content=f"Content from {doc_id} {content_version} chunk {i}",
            token_count=10,
            section_heading=f"§{i+1}",
            absolute_address=f"LOV/{doc_id}/§{i+1}",
            split_reason="none",
        )
        chunks.append(chunk.model_dump())
    return chunks


def test_embedding_incremental_updates(temp_workspace):
    """Test complete embedding cycle: initial load → updates (add/modify/remove) → verify."""

    # Setup paths
    state_file = temp_workspace / "data" / "state.json"
    embedded_state_file = temp_workspace / "data" / "embedded_files.json"
    chunks_file = temp_workspace / "data" / "chunks" / "legal_chunks.jsonl"
    enriched_file = temp_workspace / "data" / "enriched" / "embedded_chunks.jsonl"

    # Generate timestamps
    t1 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    t2 = datetime(2024, 2, 1, tzinfo=timezone.utc)

    # ========== RUN 1: Initial Chunks ==========

    # Create initial chunks for 3 documents
    chunk_writer = ChunkWriter(chunks_file)
    with chunk_writer:
        for doc_id in ["nl-doc1", "nl-doc2", "nl-doc3"]:
            chunks = create_sample_chunks(doc_id, "v1")
            for chunk in chunks:
                chunk_writer.write_chunk(ChunkMetadata(**chunk))

    # Create lovlig state
    initial_state = {
        "raw_datasets": {
            "gjeldende-lover.tar.bz2": {
                "filename": "gjeldende-lover.tar.bz2",
                "last_modified": t1.isoformat(),
                "files": {
                    "nl/nl-doc1.xml": {
                        "path": "nl/nl-doc1.xml",
                        "sha256": "hash1_v1",
                        "last_changed": t1.isoformat(),
                        "status": "added",
                    },
                    "nl/nl-doc2.xml": {
                        "path": "nl/nl-doc2.xml",
                        "sha256": "hash2_v1",
                        "last_changed": t1.isoformat(),
                        "status": "added",
                    },
                    "nl/nl-doc3.xml": {
                        "path": "nl/nl-doc3.xml",
                        "sha256": "hash3_v1",
                        "last_changed": t1.isoformat(),
                        "status": "added",
                    },
                },
            }
        }
    }

    with open(state_file, "w") as f:
        json.dump(initial_state, f, indent=2)

    # Create embedded file client
    embed_client = EmbeddedFileClient(
        embedded_state_file=embedded_state_file, lovlig_state_file=state_file
    )

    # Simulate getting files that need embedding (all 3 initially)
    changed_paths = [
        str(temp_workspace / "data" / "extracted" / "gjeldende-lover" / "nl" / "nl-doc1.xml"),
        str(temp_workspace / "data" / "extracted" / "gjeldende-lover" / "nl" / "nl-doc2.xml"),
        str(temp_workspace / "data" / "extracted" / "gjeldende-lover" / "nl" / "nl-doc3.xml"),
    ]

    files_to_embed = embed_client.get_files_needing_embedding(changed_paths, force_reembed=False)
    assert len(files_to_embed) == 3

    # Simulate embedding (with mock embeddings)
    enriched_writer = EnrichedChunkWriter(enriched_file)
    chunk_reader = ChunkReader(chunks_file)

    with enriched_writer:
        for file_meta in files_to_embed:
            doc_id = file_meta.document_id
            chunks = chunk_reader.read_chunks_for_document(doc_id)

            for chunk in chunks:
                # Mock embedding: just use [1.0, 2.0, 3.0] for testing
                enriched = {**chunk, "embedding": [1.0, 2.0, 3.0], "embedding_model": "test-model"}
                enriched_writer.write_chunk(enriched)

            # Mark as embedded
            embed_client.mark_file_embedded(
                dataset_name="gjeldende-lover.tar.bz2",
                file_path=f"nl/{doc_id}.xml",
                file_hash=initial_state["raw_datasets"]["gjeldende-lover.tar.bz2"]["files"][
                    f"nl/{doc_id}.xml"
                ]["sha256"],
                chunk_count=len(chunks),
                model_name="test-model",
                embedded_at=t1.isoformat(),
            )

    # Verify initial embeddings
    enriched_run1 = []
    with open(enriched_file) as f:
        for line in f:
            enriched_run1.append(json.loads(line))

    assert len(enriched_run1) == 6  # 3 docs * 2 chunks each
    assert all("embedding" in chunk for chunk in enriched_run1)
    assert {c["document_id"] for c in enriched_run1} == {"nl-doc1", "nl-doc2", "nl-doc3"}

    # Verify all files are marked as embedded
    files_to_embed_after = embed_client.get_files_needing_embedding(
        changed_paths, force_reembed=False
    )
    assert len(files_to_embed_after) == 0

    # ========== RUN 2: Dataset Updates ==========

    # Modify doc1's chunks
    chunk_writer = ChunkWriter(chunks_file)
    doc1_removed = chunk_writer.remove_chunks_for_document("nl-doc1")
    assert doc1_removed == 2

    with chunk_writer:
        new_chunks = create_sample_chunks("nl-doc1", "v2")  # New version
        for chunk in new_chunks:
            chunk_writer.write_chunk(ChunkMetadata(**chunk))

    # Remove doc2's chunks
    doc2_removed = chunk_writer.remove_chunks_for_document("nl-doc2")
    assert doc2_removed == 2

    # Add doc4's chunks
    with chunk_writer:
        new_chunks = create_sample_chunks("nl-doc4", "v1")
        for chunk in new_chunks:
            chunk_writer.write_chunk(ChunkMetadata(**chunk))

    # Update lovlig state
    updated_state = {
        "raw_datasets": {
            "gjeldende-lover.tar.bz2": {
                "filename": "gjeldende-lover.tar.bz2",
                "last_modified": t2.isoformat(),
                "files": {
                    "nl/nl-doc1.xml": {
                        "path": "nl/nl-doc1.xml",
                        "sha256": "hash1_v2",  # Changed hash
                        "last_changed": t2.isoformat(),
                        "status": "modified",
                    },
                    "nl/nl-doc2.xml": {
                        "path": "nl/nl-doc2.xml",
                        "sha256": "hash2_v1",
                        "last_changed": t2.isoformat(),
                        "status": "removed",
                    },
                    "nl/nl-doc3.xml": {
                        "path": "nl/nl-doc3.xml",
                        "sha256": "hash3_v1",  # Same hash
                        "last_changed": t1.isoformat(),
                        "status": "unchanged",
                    },
                    "nl/nl-doc4.xml": {
                        "path": "nl/nl-doc4.xml",
                        "sha256": "hash4_v1",
                        "last_changed": t2.isoformat(),
                        "status": "added",
                    },
                },
            }
        }
    }

    with open(state_file, "w") as f:
        json.dump(updated_state, f, indent=2)

    # Clean removed files
    removed_count = embed_client.clean_removed_files()
    assert removed_count == 1  # doc2 cleaned from embedded state

    # Get files needing embedding
    changed_paths_run2 = [
        str(temp_workspace / "data" / "extracted" / "gjeldende-lover" / "nl" / "nl-doc1.xml"),
        str(temp_workspace / "data" / "extracted" / "gjeldende-lover" / "nl" / "nl-doc3.xml"),
        str(temp_workspace / "data" / "extracted" / "gjeldende-lover" / "nl" / "nl-doc4.xml"),
    ]

    files_to_embed_run2 = embed_client.get_files_needing_embedding(
        changed_paths_run2, force_reembed=False
    )

    # Should embed: doc1 (hash changed), doc4 (new)
    # Should skip: doc3 (hash same)
    assert len(files_to_embed_run2) == 2
    doc_ids = {f.document_id for f in files_to_embed_run2}
    assert doc_ids == {"nl-doc1", "nl-doc4"}

    # Remove old embeddings for deleted file (doc2)
    removed_embeddings = {
        "document_id": "nl-doc2",
        "relative_path": "nl/nl-doc2.xml",
        "dataset_name": "gjeldende-lover.tar.bz2",
        "last_hash": "hash2_v1",
    }

    writer = EnrichedChunkWriter(enriched_file)
    removed = writer.remove_chunks_for_document("nl-doc2")
    assert removed == 2

    # Remove old embeddings for modified files
    for file_meta in files_to_embed_run2:
        removed = writer.remove_chunks_for_document(file_meta.document_id)

    # Write new embeddings
    with writer:
        for file_meta in files_to_embed_run2:
            doc_id = file_meta.document_id
            chunks = chunk_reader.read_chunks_for_document(doc_id)

            for chunk in chunks:
                enriched = {**chunk, "embedding": [4.0, 5.0, 6.0], "embedding_model": "test-model"}
                writer.write_chunk(enriched)

            # Mark as embedded
            file_path = f"nl/{doc_id}.xml"
            file_hash = updated_state["raw_datasets"]["gjeldende-lover.tar.bz2"]["files"][
                file_path
            ]["sha256"]

            embed_client.mark_file_embedded(
                dataset_name="gjeldende-lover.tar.bz2",
                file_path=file_path,
                file_hash=file_hash,
                chunk_count=len(chunks),
                model_name="test-model",
                embedded_at=t2.isoformat(),
            )

    # Verify final enriched chunks
    enriched_run2 = []
    with open(enriched_file) as f:
        for line in f:
            enriched_run2.append(json.loads(line))

    # Should have 6 chunks:
    # - nl-doc1: 2 chunks (v2, re-embedded)
    # - nl-doc2: 0 chunks (removed)
    # - nl-doc3: 2 chunks (v1, unchanged)
    # - nl-doc4: 2 chunks (v1, new)
    assert len(enriched_run2) == 6

    doc_ids = {c["document_id"] for c in enriched_run2}
    assert doc_ids == {"nl-doc1", "nl-doc3", "nl-doc4"}

    # Verify content versions
    doc1_chunks = [c for c in enriched_run2 if c["document_id"] == "nl-doc1"]
    assert len(doc1_chunks) == 2
    assert "v2" in doc1_chunks[0]["content"]

    doc2_chunks = [c for c in enriched_run2 if c["document_id"] == "nl-doc2"]
    assert len(doc2_chunks) == 0  # Removed

    doc3_chunks = [c for c in enriched_run2 if c["document_id"] == "nl-doc3"]
    assert len(doc3_chunks) == 2
    assert "v1" in doc3_chunks[0]["content"]

    doc4_chunks = [c for c in enriched_run2 if c["document_id"] == "nl-doc4"]
    assert len(doc4_chunks) == 2
    assert "v1" in doc4_chunks[0]["content"]

    # Verify no files need embedding after run 2
    files_to_embed_final = embed_client.get_files_needing_embedding(
        changed_paths_run2, force_reembed=False
    )
    assert len(files_to_embed_final) == 0


def test_force_reembed_flag(temp_workspace):
    """Test that force_reembed flag re-embeds all files."""

    state_file = temp_workspace / "data" / "state.json"
    embedded_state_file = temp_workspace / "data" / "embedded_files.json"

    # Create state with embedded files
    state = {
        "raw_datasets": {
            "gjeldende-lover.tar.bz2": {
                "files": {
                    "nl/nl-doc1.xml": {"sha256": "hash1", "status": "added"},
                }
            }
        }
    }

    embedded_state = {
        "gjeldende-lover.tar.bz2": {
            "nl/nl-doc1.xml": {
                "file_hash": "hash1",  # Same hash
                "embedded_at": "2024-01-01T00:00:00+00:00",
                "chunk_count": 2,
                "model_name": "test-model",
            }
        }
    }

    with open(state_file, "w") as f:
        json.dump(state, f)

    with open(embedded_state_file, "w") as f:
        json.dump(embedded_state, f)

    embed_client = EmbeddedFileClient(
        embedded_state_file=embedded_state_file, lovlig_state_file=state_file
    )

    changed_paths = [
        str(temp_workspace / "data" / "extracted" / "gjeldende-lover" / "nl" / "nl-doc1.xml")
    ]

    # Without force_reembed: should skip (hash matches)
    files_normal = embed_client.get_files_needing_embedding(changed_paths, force_reembed=False)
    assert len(files_normal) == 0

    # With force_reembed: should include (forced)
    files_forced = embed_client.get_files_needing_embedding(changed_paths, force_reembed=True)
    assert len(files_forced) == 1
