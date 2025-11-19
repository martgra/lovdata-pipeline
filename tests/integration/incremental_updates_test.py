"""Integration tests for incremental dataset updates.

Tests the complete pipeline behavior when datasets are updated with:
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

from lovdata_pipeline.domain.models import ChunkMetadata, FileMetadata
from lovdata_pipeline.infrastructure.chunk_writer import ChunkWriter
from lovdata_pipeline.infrastructure.lovlig_client import LovligClient
from lovdata_pipeline.infrastructure.pipeline_manifest import PipelineManifest


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace with all necessary directories."""
    with TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)

        # Create directory structure
        (workspace / "data" / "raw").mkdir(parents=True)
        (workspace / "data" / "extracted" / "gjeldende-lover" / "nl").mkdir(parents=True)
        (workspace / "data" / "chunks").mkdir(parents=True)

        yield workspace


@pytest.fixture
def sample_xml_content():
    """Sample XML content for test files."""
    def make_xml(doc_id: str, content: str) -> str:
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<law>
    <legalArticle id="{doc_id}_art1">
        <legalP>{content}</legalP>
    </legalArticle>
</law>"""
    return make_xml


def test_incremental_updates_full_cycle(temp_workspace, sample_xml_content):
    """Test complete cycle: initial load → updates (add/modify/remove) → verify chunks."""

    # Setup paths
    state_file = temp_workspace / "data" / "state.json"
    extracted_dir = temp_workspace / "data" / "extracted"
    chunks_file = temp_workspace / "data" / "chunks" / "legal_chunks.jsonl"
    manifest_file = temp_workspace / "data" / "manifest.json"

    # Create manifest
    manifest = PipelineManifest(manifest_file=manifest_file)

    # Create lovlig client with manifest
    lovlig = LovligClient(
        dataset_filter="gjeldende",
        raw_data_dir=temp_workspace / "data" / "raw",
        extracted_data_dir=extracted_dir,
        state_file=state_file,
        max_download_concurrency=1,
        manifest=manifest,
    )

    # ========== RUN 1: Initial Dataset ==========

    # Generate timestamps
    t1 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    t2 = datetime(2024, 2, 1, tzinfo=timezone.utc)

    # Create initial files
    doc1_path = extracted_dir / "gjeldende-lover" / "nl" / "nl-doc1.xml"
    doc2_path = extracted_dir / "gjeldende-lover" / "nl" / "nl-doc2.xml"
    doc3_path = extracted_dir / "gjeldende-lover" / "nl" / "nl-doc3.xml"

    doc1_path.write_text(sample_xml_content("nl-doc1", "Initial content for doc1"))
    doc2_path.write_text(sample_xml_content("nl-doc2", "Initial content for doc2"))
    doc3_path.write_text(sample_xml_content("nl-doc3", "Initial content for doc3"))

    # Create initial lovlig state (simulating first sync)
    initial_state = {
        "raw_datasets": {
            "gjeldende-lover.tar.bz2": {
                "filename": "gjeldende-lover.tar.bz2",
                "last_modified": t1.isoformat(),
                "files": {
                    "nl/nl-doc1.xml": {
                        "path": "nl/nl-doc1.xml",
                        "size": doc1_path.stat().st_size,
                        "sha256": "hash1_v1",
                        "last_changed": t1.isoformat(),
                        "status": "added",
                    },
                    "nl/nl-doc2.xml": {
                        "path": "nl/nl-doc2.xml",
                        "size": doc2_path.stat().st_size,
                        "sha256": "hash2_v1",
                        "last_changed": t1.isoformat(),
                        "status": "added",
                    },
                    "nl/nl-doc3.xml": {
                        "path": "nl/nl-doc3.xml",
                        "size": doc3_path.stat().st_size,
                        "sha256": "hash3_v1",
                        "last_changed": t1.isoformat(),
                        "status": "added",
                    },
                }
            }
        }
    }

    with open(state_file, "w") as f:
        json.dump(initial_state, f, indent=2)

    # Process initial files (simulate chunking asset)
    unprocessed_files = lovlig.get_unprocessed_files(force_reprocess=False)
    assert len(unprocessed_files) == 3

    # Write chunks for initial files
    writer = ChunkWriter(chunks_file)
    with writer:
        for file_meta in unprocessed_files:
            doc_id = Path(file_meta.relative_path).stem
            chunk = ChunkMetadata(
                chunk_id=f"{doc_id}_chunk1",
                document_id=doc_id,
                content=f"Chunk from {doc_id} version 1",
                token_count=10,
                section_heading="§1",
                absolute_address=f"LOV/{doc_id}/§1",
                split_reason="none",
            )
            writer.write_chunk(chunk)

            # Mark as processed
            lovlig.mark_file_processed(file_meta.dataset_name, file_meta.relative_path)

    # Verify initial chunks
    chunks_run1 = []
    with open(chunks_file) as f:
        for line in f:
            chunks_run1.append(json.loads(line))

    assert len(chunks_run1) == 3
    assert {c["document_id"] for c in chunks_run1} == {"nl-doc1", "nl-doc2", "nl-doc3"}

    # Verify all files are marked as processed
    unprocessed_after_run1 = lovlig.get_unprocessed_files(force_reprocess=False)
    assert len(unprocessed_after_run1) == 0

    # ========== RUN 2: Dataset Updates ==========

    # Modify doc1 (new content)
    doc1_path.write_text(sample_xml_content("nl-doc1", "MODIFIED content for doc1"))

    # Remove doc2
    doc2_path.unlink()

    # Add doc4
    doc4_path = extracted_dir / "gjeldende-lover" / "nl" / "nl-doc4.xml"
    doc4_path.write_text(sample_xml_content("nl-doc4", "New content for doc4"))

    # Update lovlig state (simulating second sync with changes)
    updated_state = {
        "raw_datasets": {
            "gjeldende-lover.tar.bz2": {
                "filename": "gjeldende-lover.tar.bz2",
                "last_modified": t2.isoformat(),
                "files": {
                    "nl/nl-doc1.xml": {
                        "path": "nl/nl-doc1.xml",
                        "size": doc1_path.stat().st_size,
                        "sha256": "hash1_v2",  # Changed hash
                        "last_changed": t2.isoformat(),  # Newer timestamp
                        "status": "modified",  # Changed status
                    },
                    "nl/nl-doc2.xml": {
                        "path": "nl/nl-doc2.xml",
                        "size": 0,
                        "sha256": "hash2_v1",
                        "last_changed": t2.isoformat(),
                        "status": "removed",  # Removed
                    },
                    "nl/nl-doc3.xml": {
                        "path": "nl/nl-doc3.xml",
                        "size": doc3_path.stat().st_size,
                        "sha256": "hash3_v1",
                        "last_changed": t1.isoformat(),  # Unchanged timestamp
                        "status": "unchanged",
                    },
                    "nl/nl-doc4.xml": {
                        "path": "nl/nl-doc4.xml",
                        "size": doc4_path.stat().st_size,
                        "sha256": "hash4_v1",
                        "last_changed": t2.isoformat(),
                        "status": "added",  # New file
                    },
                }
            }
        }
    }

    with open(state_file, "w") as f:
        json.dump(updated_state, f, indent=2)

    # Clean up removed files from processing state
    removed_count = lovlig.clean_removed_files_from_processed_state()
    assert removed_count == 1  # doc2 should be cleaned

    # Get unprocessed files after update
    unprocessed_files_run2 = lovlig.get_unprocessed_files(force_reprocess=False)

    # Should have: doc1 (modified) and doc4 (added)
    # Should NOT have: doc2 (removed), doc3 (unchanged and already processed)
    assert len(unprocessed_files_run2) == 2
    unprocessed_paths = {Path(f.relative_path).stem for f in unprocessed_files_run2}
    assert unprocessed_paths == {"nl-doc1", "nl-doc4"}

    # Get removed files for cleanup
    removed_files = lovlig.get_removed_files()
    assert len(removed_files) == 1
    assert removed_files[0].document_id == "nl-doc2"

    # Process updated files WITH removal metadata
    writer = ChunkWriter(chunks_file)

    # Remove old chunks BEFORE opening writer
    # Pass 1A: Remove chunks for deleted files
    for removal_info in removed_files:
        removed = writer.remove_chunks_for_document(removal_info.document_id)
        # Should remove 1 chunk for nl-doc2

    # Pass 1B: Remove chunks for modified files
    for file_meta in unprocessed_files_run2:
        doc_id = Path(file_meta.relative_path).stem
        removed_chunks = writer.remove_chunks_for_document(doc_id)

    # Now write new chunks
    with writer:
        for file_meta in unprocessed_files_run2:
            doc_id = Path(file_meta.relative_path).stem

            # Write new chunks
            chunk = ChunkMetadata(
                chunk_id=f"{doc_id}_chunk1",
                document_id=doc_id,
                content=f"Chunk from {doc_id} version 2",
                token_count=10,
                section_heading="§1",
                absolute_address=f"LOV/{doc_id}/§1",
                split_reason="none",
            )
            writer.write_chunk(chunk)

            # Mark as processed
            lovlig.mark_file_processed(file_meta.dataset_name, file_meta.relative_path)

    # Verify final chunks
    chunks_run2 = []
    with open(chunks_file) as f:
        for line in f:
            chunks_run2.append(json.loads(line))

    # Should have 3 chunks (nl-doc2 removed):
    # - nl-doc1 (version 2, modified)
    # - nl-doc3 (version 1, unchanged)
    # - nl-doc4 (version 2, new)
    assert len(chunks_run2) == 3

    doc_ids = {c["document_id"] for c in chunks_run2}
    assert doc_ids == {"nl-doc1", "nl-doc3", "nl-doc4"}

    # Verify content versions
    doc1_chunks = [c for c in chunks_run2 if c["document_id"] == "nl-doc1"]
    assert len(doc1_chunks) == 1
    assert "version 2" in doc1_chunks[0]["content"]  # Modified

    doc2_chunks = [c for c in chunks_run2 if c["document_id"] == "nl-doc2"]
    assert len(doc2_chunks) == 0  # Removed file chunks deleted

    doc3_chunks = [c for c in chunks_run2 if c["document_id"] == "nl-doc3"]
    assert len(doc3_chunks) == 1
    assert "version 1" in doc3_chunks[0]["content"]  # Unchanged

    doc4_chunks = [c for c in chunks_run2 if c["document_id"] == "nl-doc4"]
    assert len(doc4_chunks) == 1
    assert "version 2" in doc4_chunks[0]["content"]  # New file

    # Verify no unprocessed files remain
    unprocessed_after_run2 = lovlig.get_unprocessed_files(force_reprocess=False)
    assert len(unprocessed_after_run2) == 0

    # Verify removed files were identified
    removed_files_final = lovlig.get_removed_files()
    assert len(removed_files_final) == 1
    assert removed_files_final[0].document_id == "nl-doc2"


def test_multiple_modifications_same_document(temp_workspace, sample_xml_content):
    """Test that multiple modifications to the same document work correctly."""
    from datetime import datetime, timezone

    # Create consistent timeline - each version 1 month apart
    t1 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    t2 = datetime(2024, 2, 1, tzinfo=timezone.utc)
    t3 = datetime(2024, 3, 1, tzinfo=timezone.utc)
    timestamps = [t1, t2, t3]

    state_file = temp_workspace / "data" / "state.json"
    extracted_dir = temp_workspace / "data" / "extracted"
    chunks_file = temp_workspace / "data" / "chunks" / "legal_chunks.jsonl"
    manifest_file = temp_workspace / "data" / "manifest.json"

    doc_path = extracted_dir / "gjeldende-lover" / "nl" / "nl-test.xml"
    doc_path.write_text(sample_xml_content("nl-test", "Version 1"))

    # Create manifest
    manifest = PipelineManifest(manifest_file=manifest_file)

    lovlig = LovligClient(
        dataset_filter="gjeldende",
        raw_data_dir=temp_workspace / "data" / "raw",
        extracted_data_dir=extracted_dir,
        state_file=state_file,
        max_download_concurrency=1,
        manifest=manifest,
    )

    # Run through 3 versions
    for version in range(1, 4):
        # Update content
        doc_path.write_text(sample_xml_content("nl-test", f"Version {version}"))

        # Update state with proper timestamp
        state = {
            "raw_datasets": {
                "gjeldende-lover.tar.bz2": {
                    "filename": "gjeldende-lover.tar.bz2",
                    "last_modified": timestamps[version-1].isoformat(),
                    "files": {
                        "nl/nl-test.xml": {
                            "path": "nl/nl-test.xml",
                            "size": doc_path.stat().st_size,
                            "sha256": f"hash_v{version}",
                            "last_changed": timestamps[version-1].isoformat(),
                            "status": "added" if version == 1 else "modified",
                        },
                    }
                }
            }
        }

        with open(state_file, "w") as f:
            json.dump(state, f, indent=2)

        # Process
        unprocessed = lovlig.get_unprocessed_files(force_reprocess=False)
        assert len(unprocessed) == 1

        writer = ChunkWriter(chunks_file)

        # Remove old chunks BEFORE opening writer
        removed = writer.remove_chunks_for_document("nl-test")
        if version > 1:
            assert removed == 1

        # Write new chunks
        with writer:
            chunk = ChunkMetadata(
                chunk_id=f"nl-test_v{version}",
                document_id="nl-test",
                content=f"Content version {version}",
                token_count=10,
                section_heading="§1",
                absolute_address="LOV/nl-test/§1",
                split_reason="none",
            )
            writer.write_chunk(chunk)

        # Mark as processed with timestamp before next update
        lovlig.mark_file_processed("gjeldende-lover.tar.bz2", "nl/nl-test.xml")

        # Verify only latest version exists
        chunks = []
        with open(chunks_file) as f:
            for line in f:
                chunks.append(json.loads(line))

        assert len(chunks) == 1
        assert chunks[0]["content"] == f"Content version {version}"
