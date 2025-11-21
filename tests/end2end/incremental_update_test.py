"""End-to-end test for incremental update workflow.

This test validates the complete incremental update feature by simulating
a real-world scenario with multiple pipeline runs:
1. Initial pipeline run with some files
2. Add new files
3. Modify existing files
4. Remove some files
5. Verify only changed files are processed
6. Verify state consistency
7. Verify vector store consistency
"""

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from lovdata_pipeline.domain.models import (
    FileProcessingResult,
    LovligFileInfo,
    LovligRemovedFileInfo,
    LovligSyncStats,
    PipelineConfig,
)
from lovdata_pipeline.domain.services.chunking_service import ChunkingService
from lovdata_pipeline.domain.services.embedding_service import EmbeddingService
from lovdata_pipeline.domain.services.file_processing_service import FileProcessingService
from lovdata_pipeline.infrastructure.jsonl_vector_store import JsonlVectorStoreRepository
from lovdata_pipeline.infrastructure.openai_embedding_provider import OpenAIEmbeddingProvider
from lovdata_pipeline.orchestration.pipeline_orchestrator import PipelineOrchestrator
from lovdata_pipeline.state import ProcessingState


def create_sample_law_xml(doc_id: str, content: str) -> str:
    """Create sample XML content for testing."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html lang="no">
<head><title>{doc_id}</title></head>
<body>
    <main class="documentBody" id="dokument">
        <h1>Test Law {doc_id}</h1>
        <section class="section">
            <h2>Kapittel 1</h2>
            <article class="legalArticle" data-lovdata-URL="NL/lov/{doc_id}/§1" id="paragraf-1">
                <h2 class="legalArticleHeader">
                    <span class="legalArticleValue">§ 1</span>
                </h2>
                <article class="legalP" id="ledd-1">
                    {content}
                </article>
            </article>
        </section>
    </main>
</body>
</html>"""


def create_lovlig_state(
    state_file: Path,
    dataset_dir: Path,
    files_config: dict[str, tuple[str, str]],
) -> None:
    """Create lovlig state.json file.

    Args:
        state_file: Path to state.json
        dataset_dir: Directory where files are located
        files_config: Dict mapping relative_path to (status, hash)
    """
    # Note: We'll mock lovlig in tests, so this is just for documentation
    pass


def create_mock_lovlig(extracted_dir: Path, files_config: dict[str, tuple[str, str]]):
    """Create a mock Lovlig client that simulates incremental updates.

    Args:
        extracted_dir: Directory where XML files are located
        files_config: Dict mapping relative_path to (status, hash)

    Returns:
        Mock Lovlig client
    """
    mock_lovlig = Mock()
    mock_lovlig.state_file = extracted_dir.parent.parent / "state.json"
    mock_lovlig.state_file.touch()

    # Build changed and removed file lists based on status
    changed_files = []
    removed_files = []
    all_files = []

    for rel_path, (status, file_hash) in files_config.items():
        doc_id = Path(rel_path).stem
        abs_path = extracted_dir / rel_path

        if status in ("added", "modified"):
            changed_files.append(
                LovligFileInfo(
                    doc_id=doc_id,
                    path=abs_path,
                    hash=file_hash,
                    dataset="test-dataset.tar.bz2",
                )
            )

        if status == "removed":
            removed_files.append(
                LovligRemovedFileInfo(
                    doc_id=doc_id,
                    dataset="test-dataset.tar.bz2",
                )
            )

        # All files except removed
        if status != "removed":
            all_files.append(
                LovligFileInfo(
                    doc_id=doc_id,
                    path=abs_path,
                    hash=file_hash,
                    dataset="test-dataset.tar.bz2",
                )
            )

    mock_lovlig.get_changed_files.return_value = changed_files
    mock_lovlig.get_removed_files.return_value = removed_files
    mock_lovlig.get_all_files.return_value = all_files

    # Calculate sync stats from status counts
    stats = {"added": 0, "modified": 0, "removed": 0}
    for _, (status, _) in files_config.items():
        if status in stats:
            stats[status] += 1

    mock_lovlig.sync.return_value = LovligSyncStats(**stats)

    return mock_lovlig


# E2E-specific pipeline services fixture
@pytest.fixture
def pipeline_services(tmp_path, mock_openai_client):
    """Create real pipeline services for E2E testing."""
    # Create vector store
    vector_store = JsonlVectorStoreRepository(tmp_path / "vectors")

    # Create chunking service
    chunking_service = ChunkingService(target_tokens=512, max_tokens=1000)

    # Create embedding service
    embedding_provider = OpenAIEmbeddingProvider(mock_openai_client, "test-model")
    embedding_service = EmbeddingService(provider=embedding_provider, batch_size=100)

    # Create file processor
    file_processor = FileProcessingService(
        chunking_service=chunking_service,
        embedding_service=embedding_service,
        vector_store=vector_store,
    )

    # Create orchestrator
    orchestrator = PipelineOrchestrator(
        file_processor=file_processor,
        vector_store=vector_store,
    )

    return {
        "orchestrator": orchestrator,
        "vector_store": vector_store,
        "file_processor": file_processor,
    }


@patch("lovdata_pipeline.orchestration.pipeline_orchestrator.Lovlig")
def test_incremental_update_full_workflow(mock_lovlig_class, tmp_path, pipeline_services):
    """Test complete incremental update workflow.

    Scenario:
    1. Initial run: Process 3 documents
    2. Second run: Add 1 new, modify 1 existing, remove 1 old
    3. Verify only changed files processed
    4. Verify state consistency
    5. Verify vector store consistency
    """
    orchestrator = pipeline_services["orchestrator"]
    vector_store = pipeline_services["vector_store"]

    # Setup directory structure
    data_dir = tmp_path / "data"
    extracted_dir = data_dir / "extracted" / "test-dataset"
    extracted_dir.mkdir(parents=True)

    pipeline_state_file = data_dir / "pipeline_state.json"

    config = PipelineConfig(
        data_dir=data_dir,
        dataset_filter="test",
        force=False,
        limit=None,
    )

    # ==========================================
    # PHASE 1: Initial pipeline run with 3 files
    # ==========================================

    print("\n=== PHASE 1: Initial Run ===")

    # Create 3 initial XML files
    doc1_path = extracted_dir / "doc1.xml"
    doc1_path.write_text(create_sample_law_xml("doc1", "Initial content for document 1"))

    doc2_path = extracted_dir / "doc2.xml"
    doc2_path.write_text(create_sample_law_xml("doc2", "Initial content for document 2"))

    doc3_path = extracted_dir / "doc3.xml"
    doc3_path.write_text(create_sample_law_xml("doc3", "Initial content for document 3"))

    # Mock lovlig showing all 3 as "added"
    mock_lovlig = create_mock_lovlig(
        extracted_dir,
        {
            "doc1.xml": ("added", "hash1_v1"),
            "doc2.xml": ("added", "hash2_v1"),
            "doc3.xml": ("added", "hash3_v1"),
        },
    )
    mock_lovlig_class.return_value = mock_lovlig

    # Run pipeline - should process all 3 files
    result1 = orchestrator.run(config)

    # Verify results
    assert result1.processed == 3, "Should process all 3 new files"
    assert result1.failed == 0, "No files should fail"
    assert result1.removed == 0, "No files removed yet"

    # Verify state
    state1 = ProcessingState(pipeline_state_file)
    assert len(state1.state.processed) == 3, "All 3 should be in processed state"
    assert "doc1" in state1.state.processed
    assert "doc2" in state1.state.processed
    assert "doc3" in state1.state.processed
    assert state1.state.processed["doc1"].hash == "hash1_v1"

    # Verify vector store
    initial_vector_count = vector_store.count()
    assert initial_vector_count > 0, "Should have vectors stored"

    doc1_chunks_initial = vector_store.get_chunks_by_document_id("doc1")
    doc2_chunks_initial = vector_store.get_chunks_by_document_id("doc2")
    doc3_chunks_initial = vector_store.get_chunks_by_document_id("doc3")

    assert len(doc1_chunks_initial) > 0, "doc1 should have chunks"
    assert len(doc2_chunks_initial) > 0, "doc2 should have chunks"
    assert len(doc3_chunks_initial) > 0, "doc3 should have chunks"

    print(f"Initial run: {initial_vector_count} vectors created")
    print(f"  doc1: {len(doc1_chunks_initial)} chunks")
    print(f"  doc2: {len(doc2_chunks_initial)} chunks")
    print(f"  doc3: {len(doc3_chunks_initial)} chunks")

    # ==========================================
    # PHASE 2: Incremental update
    # - Add doc4 (new)
    # - Modify doc2 (changed content)
    # - Remove doc3
    # - doc1 unchanged (should be skipped)
    # ==========================================

    print("\n=== PHASE 2: Incremental Update ===")

    # Add new document
    doc4_path = extracted_dir / "doc4.xml"
    doc4_path.write_text(create_sample_law_xml("doc4", "Brand new document 4 content"))

    # Modify doc2 content
    doc2_path.write_text(create_sample_law_xml("doc2", "MODIFIED content for document 2 with more text"))

    # Remove doc3 file
    doc3_path.unlink()

    # Update mock lovlig to reflect changes
    mock_lovlig2 = create_mock_lovlig(
        extracted_dir,
        {
            "doc1.xml": ("unchanged", "hash1_v1"),  # Unchanged
            "doc2.xml": ("modified", "hash2_v2"),    # Modified (new hash)
            "doc3.xml": ("removed", "hash3_v1"),     # Removed
            "doc4.xml": ("added", "hash4_v1"),       # New file
        },
    )
    mock_lovlig_class.return_value = mock_lovlig2

    # Run pipeline again - should only process changed files
    result2 = orchestrator.run(config)

    # Verify incremental processing
    assert result2.processed == 2, "Should process only doc2 (modified) and doc4 (new)"
    assert result2.failed == 0, "No files should fail"
    assert result2.removed == 1, "doc3 should be removed"

    # Verify state after incremental update
    state2 = ProcessingState(pipeline_state_file)
    assert len(state2.state.processed) == 3, "Should have doc1, doc2, doc4"
    assert "doc1" in state2.state.processed, "doc1 should still be in state"
    assert "doc2" in state2.state.processed, "doc2 should be updated"
    assert "doc3" not in state2.state.processed, "doc3 should be removed from state"
    assert "doc4" in state2.state.processed, "doc4 should be added"

    # Verify hashes updated correctly
    assert state2.state.processed["doc1"].hash == "hash1_v1", "doc1 hash unchanged"
    assert state2.state.processed["doc2"].hash == "hash2_v2", "doc2 hash should be updated"
    assert state2.state.processed["doc4"].hash == "hash4_v1", "doc4 should have new hash"

    # Verify vector store consistency
    final_vector_count = vector_store.count()

    doc1_chunks_final = vector_store.get_chunks_by_document_id("doc1")
    doc2_chunks_final = vector_store.get_chunks_by_document_id("doc2")
    doc3_chunks_final = vector_store.get_chunks_by_document_id("doc3")
    doc4_chunks_final = vector_store.get_chunks_by_document_id("doc4")

    # doc1 should be unchanged
    assert len(doc1_chunks_final) == len(doc1_chunks_initial), "doc1 chunks should be unchanged"
    assert doc1_chunks_final[0].chunk_id == doc1_chunks_initial[0].chunk_id

    # doc2 should be updated (could have different chunk count due to modified content)
    assert len(doc2_chunks_final) > 0, "doc2 should have chunks"
    # The old doc2 chunks should be replaced
    if len(doc2_chunks_final) == len(doc2_chunks_initial):
        # If same count, content should be different
        assert doc2_chunks_final[0].content != doc2_chunks_initial[0].content, \
            "doc2 content should be updated"

    # doc3 should be completely removed
    assert len(doc3_chunks_final) == 0, "doc3 should have no chunks (removed)"

    # doc4 should be added
    assert len(doc4_chunks_final) > 0, "doc4 should have chunks"

    print(f"\nIncremental update: {final_vector_count} total vectors")
    print(f"  doc1: {len(doc1_chunks_final)} chunks (unchanged)")
    print(f"  doc2: {len(doc2_chunks_final)} chunks (modified)")
    print(f"  doc3: {len(doc3_chunks_final)} chunks (removed)")
    print(f"  doc4: {len(doc4_chunks_final)} chunks (new)")

    # Verify no orphaned vectors
    all_hashes = vector_store.list_hashes()
    print(f"\nVector store hashes: {all_hashes}")

    # Should have vectors for doc1, doc2, doc4 (all with their current hashes)
    # doc3's hash should not be present
    expected_docs = {"doc1", "doc2", "doc4"}
    actual_docs = set()
    for hash_val in all_hashes:
        chunks = vector_store.get_chunks_by_hash(hash_val)
        if chunks:
            actual_docs.add(chunks[0].document_id)

    assert actual_docs == expected_docs, f"Vector store should only have {expected_docs}, got {actual_docs}"

    print("\n✅ Incremental update workflow validated successfully!")


@patch("lovdata_pipeline.orchestration.pipeline_orchestrator.Lovlig")
def test_incremental_update_skip_unchanged(mock_lovlig_class, tmp_path, pipeline_services):
    """Test that unchanged files are skipped in incremental updates."""
    orchestrator = pipeline_services["orchestrator"]
    vector_store = pipeline_services["vector_store"]

    # Setup
    data_dir = tmp_path / "data"
    extracted_dir = data_dir / "extracted" / "test-dataset"
    extracted_dir.mkdir(parents=True)

    pipeline_state_file = data_dir / "pipeline_state.json"

    config = PipelineConfig(
        data_dir=data_dir,
        dataset_filter="test",
        force=False,
        limit=None,
    )

    # Create initial file
    doc1_path = extracted_dir / "doc1.xml"
    doc1_path.write_text(create_sample_law_xml("doc1", "Content that won't change"))

    mock_lovlig = create_mock_lovlig(
        extracted_dir,
        {"doc1.xml": ("added", "hash1")},
    )
    mock_lovlig_class.return_value = mock_lovlig

    # First run
    result1 = orchestrator.run(config)
    assert result1.processed == 1

    # Update mock to show file as unchanged
    mock_lovlig2 = create_mock_lovlig(
        extracted_dir,
        {"doc1.xml": ("unchanged", "hash1")},  # Same hash
    )
    mock_lovlig_class.return_value = mock_lovlig2

    # Second run - should skip processing
    result2 = orchestrator.run(config)

    assert result2.processed == 0, "Should skip unchanged file"
    assert result2.failed == 0
    assert result2.removed == 0

    # Verify state didn't change
    state = ProcessingState(pipeline_state_file)
    assert state.state.processed["doc1"].hash == "hash1"


@patch("lovdata_pipeline.orchestration.pipeline_orchestrator.Lovlig")
def test_incremental_update_force_reprocess(mock_lovlig_class, tmp_path, pipeline_services):
    """Test that force flag reprocesses all files including unchanged ones."""
    orchestrator = pipeline_services["orchestrator"]

    # Setup
    data_dir = tmp_path / "data"
    extracted_dir = data_dir / "extracted" / "test-dataset"
    extracted_dir.mkdir(parents=True)

    config = PipelineConfig(
        data_dir=data_dir,
        dataset_filter="test",
        force=False,
        limit=None,
    )

    # Create 2 files
    doc1_path = extracted_dir / "doc1.xml"
    doc1_path.write_text(create_sample_law_xml("doc1", "Content 1"))

    doc2_path = extracted_dir / "doc2.xml"
    doc2_path.write_text(create_sample_law_xml("doc2", "Content 2"))

    mock_lovlig = create_mock_lovlig(
        extracted_dir,
        {
            "doc1.xml": ("added", "hash1"),
            "doc2.xml": ("added", "hash2"),
        },
    )
    mock_lovlig_class.return_value = mock_lovlig

    # First run
    result1 = orchestrator.run(config)
    assert result1.processed == 2

    # Mark both as unchanged
    mock_lovlig2 = create_mock_lovlig(
        extracted_dir,
        {
            "doc1.xml": ("unchanged", "hash1"),
            "doc2.xml": ("unchanged", "hash2"),
        },
    )
    mock_lovlig_class.return_value = mock_lovlig2

    # Normal run should skip both
    result2 = orchestrator.run(config)
    assert result2.processed == 0, "Should skip both unchanged files"

    # Force run should reprocess both
    config.force = True
    result3 = orchestrator.run(config)
    assert result3.processed == 2, "Force should reprocess all files"


@patch("lovdata_pipeline.orchestration.pipeline_orchestrator.Lovlig")
def test_incremental_update_retry_failed(mock_lovlig_class, tmp_path, pipeline_services):
    """Test that previously failed files are retried in incremental updates."""
    orchestrator = pipeline_services["orchestrator"]
    file_processor = pipeline_services["file_processor"]

    # Setup
    data_dir = tmp_path / "data"
    extracted_dir = data_dir / "extracted" / "test-dataset"
    extracted_dir.mkdir(parents=True)

    pipeline_state_file = data_dir / "pipeline_state.json"

    config = PipelineConfig(
        data_dir=data_dir,
        dataset_filter="test",
        force=False,
        limit=None,
    )

    # Create a file
    doc1_path = extracted_dir / "doc1.xml"
    # Create malformed XML initially
    doc1_path.write_text("This is not valid XML!")

    mock_lovlig = create_mock_lovlig(
        extracted_dir,
        {"doc1.xml": ("added", "hash1_bad")},
    )
    mock_lovlig_class.return_value = mock_lovlig

    # First run - should fail
    result1 = orchestrator.run(config)
    assert result1.failed == 1, "Should fail with invalid XML"
    assert result1.processed == 0

    # Verify it's in failed state
    state1 = ProcessingState(pipeline_state_file)
    assert "doc1" in state1.state.failed

    # Fix the file
    doc1_path.write_text(create_sample_law_xml("doc1", "Now valid content"))

    mock_lovlig2 = create_mock_lovlig(
        extracted_dir,
        {"doc1.xml": ("modified", "hash1_good")},  # New hash for fixed content
    )
    mock_lovlig_class.return_value = mock_lovlig2

    # Second run - should retry and succeed
    result2 = orchestrator.run(config)
    assert result2.processed == 1, "Should retry and succeed"
    assert result2.failed == 0

    # Verify it moved from failed to processed
    state2 = ProcessingState(pipeline_state_file)
    assert "doc1" not in state2.state.failed
    assert "doc1" in state2.state.processed
    assert state2.state.processed["doc1"].hash == "hash1_good"
