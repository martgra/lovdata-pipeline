"""Unit tests for chunk writer."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from lovdata_pipeline.domain.models import ChunkMetadata
from lovdata_pipeline.infrastructure.chunk_writer import ChunkWriter


@pytest.fixture
def temp_output_dir():
    """Create a temporary directory for test output."""
    with TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_chunks():
    """Create sample chunks for testing."""
    return [
        ChunkMetadata(
            chunk_id="doc1_art1",
            document_id="doc1",
            content="First chunk content",
            token_count=10,
            section_heading="§ 1",
            absolute_address="LOV/2024/§1",
            split_reason="none",
        ),
        ChunkMetadata(
            chunk_id="doc1_art2",
            document_id="doc1",
            content="Second chunk content",
            token_count=12,
            section_heading="§ 2",
            absolute_address="LOV/2024/§2",
            split_reason="none",
        ),
        ChunkMetadata(
            chunk_id="doc1_art3_sub_001",
            document_id="doc1",
            content="Third chunk content (sub-chunk)",
            token_count=15,
            section_heading="§ 3",
            absolute_address="LOV/2024/§3",
            split_reason="paragraph",
            parent_chunk_id="doc1_art3",
        ),
    ]


def test_chunk_writer_initialization(temp_output_dir):
    """Test ChunkWriter initialization."""
    output_path = temp_output_dir / "test.jsonl"
    writer = ChunkWriter(output_path)

    assert writer.output_path == output_path
    assert writer.file_handle is None
    assert writer.chunks_written == 0


def test_chunk_writer_context_manager(temp_output_dir, sample_chunks):
    """Test ChunkWriter as context manager."""
    output_path = temp_output_dir / "test.jsonl"

    with ChunkWriter(output_path) as writer:
        writer.write_chunk(sample_chunks[0])
        assert writer.chunks_written == 1

    # File should be closed after context
    assert output_path.exists()


def test_write_single_chunk(temp_output_dir, sample_chunks):
    """Test writing a single chunk."""
    output_path = temp_output_dir / "test.jsonl"
    writer = ChunkWriter(output_path)

    writer.open()
    writer.write_chunk(sample_chunks[0])
    writer.close()

    assert output_path.exists()
    assert writer.chunks_written == 1

    # Verify content
    with open(output_path, "r", encoding="utf-8") as f:
        line = f.readline()
        data = json.loads(line)

    assert data["chunk_id"] == "doc1_art1"
    assert data["content"] == "First chunk content"
    assert data["token_count"] == 10


def test_write_multiple_chunks(temp_output_dir, sample_chunks):
    """Test writing multiple chunks."""
    output_path = temp_output_dir / "test.jsonl"

    with ChunkWriter(output_path) as writer:
        writer.write_chunks(sample_chunks)

    assert writer.chunks_written == 3

    # Verify all chunks were written
    with open(output_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    assert len(lines) == 3

    # Verify first and last chunk
    first = json.loads(lines[0])
    last = json.loads(lines[2])

    assert first["chunk_id"] == "doc1_art1"
    assert last["chunk_id"] == "doc1_art3_sub_001"
    assert last["parent_chunk_id"] == "doc1_art3"


def test_append_mode(temp_output_dir, sample_chunks):
    """Test append mode."""
    output_path = temp_output_dir / "test.jsonl"

    # Write first chunk
    with ChunkWriter(output_path) as writer:
        writer.write_chunk(sample_chunks[0])

    # Append more chunks
    with ChunkWriter(output_path) as writer:
        writer.write_chunks(sample_chunks[1:])

    # Verify all chunks are present
    with open(output_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    assert len(lines) == 3


def test_overwrite_mode(temp_output_dir, sample_chunks):
    """Test overwrite mode."""
    output_path = temp_output_dir / "test.jsonl"

    # Write first chunk
    with ChunkWriter(output_path) as writer:
        writer.write_chunk(sample_chunks[0])

    # Overwrite with new chunks
    writer = ChunkWriter(output_path)
    writer.open(mode="w")
    writer.write_chunks(sample_chunks[1:])
    writer.close()

    # Verify only new chunks are present
    with open(output_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["chunk_id"] == "doc1_art2"  # Not doc1_art1


def test_clear_file(temp_output_dir, sample_chunks):
    """Test clearing the output file."""
    output_path = temp_output_dir / "test.jsonl"

    # Write some data
    with ChunkWriter(output_path) as writer:
        writer.write_chunks(sample_chunks)

    assert output_path.exists()

    # Clear the file
    writer = ChunkWriter(output_path)
    writer.clear()

    assert not output_path.exists()


def test_get_file_size_mb(temp_output_dir, sample_chunks):
    """Test getting file size."""
    output_path = temp_output_dir / "test.jsonl"
    writer = ChunkWriter(output_path)

    # Before writing
    assert writer.get_file_size_mb() == 0.0

    # After writing
    with writer:
        writer.write_chunks(sample_chunks)

    size_mb = writer.get_file_size_mb()
    assert size_mb > 0
    assert isinstance(size_mb, float)


def test_write_without_open_raises_error(temp_output_dir, sample_chunks):
    """Test that writing without opening raises error."""
    output_path = temp_output_dir / "test.jsonl"
    writer = ChunkWriter(output_path)

    with pytest.raises(RuntimeError, match="File is not open"):
        writer.write_chunk(sample_chunks[0])


def test_unicode_content(temp_output_dir):
    """Test writing chunks with Unicode content."""
    output_path = temp_output_dir / "test.jsonl"

    chunk = ChunkMetadata(
        chunk_id="unicode-test",
        document_id="unicode-doc",
        content="Norwegian legal text with æøå and special characters: §, ©, €",
        token_count=20,
        section_heading="§ 1 Æøå",
        absolute_address="LOV/2024/§1",
        split_reason="none",
    )

    with ChunkWriter(output_path) as writer:
        writer.write_chunk(chunk)

    # Verify Unicode is preserved
    with open(output_path, "r", encoding="utf-8") as f:
        data = json.loads(f.readline())

    assert "æøå" in data["content"]
    assert "§" in data["content"]
    assert "Æøå" in data["section_heading"]


def test_creates_parent_directories(temp_output_dir):
    """Test that parent directories are created automatically."""
    output_path = temp_output_dir / "nested" / "deep" / "output.jsonl"

    chunk = ChunkMetadata(
        chunk_id="test",
        document_id="doc",
        content="content",
        token_count=5,
        section_heading="§1",
        absolute_address="LOV/2024/§1",
        split_reason="none",
    )

    with ChunkWriter(output_path) as writer:
        writer.write_chunk(chunk)

    assert output_path.exists()
    assert output_path.parent.exists()


def test_large_number_of_chunks(temp_output_dir):
    """Test writing a large number of chunks."""
    output_path = temp_output_dir / "large.jsonl"

    chunks = [
        ChunkMetadata(
            chunk_id=f"chunk_{i}",
            document_id=f"doc_{i // 10}",
            content=f"Content for chunk {i}",
            token_count=10 + i,
            section_heading=f"§ {i}",
            absolute_address=f"LOV/2024/§{i}",
            split_reason="none",
        )
        for i in range(1000)
    ]

    with ChunkWriter(output_path) as writer:
        writer.write_chunks(chunks)

    assert writer.chunks_written == 1000

    # Verify count by reading
    with open(output_path, "r", encoding="utf-8") as f:
        line_count = sum(1 for _ in f)

    assert line_count == 1000


def test_remove_chunks_for_document(temp_output_dir):
    """Test removing chunks for a specific document."""
    output_path = temp_output_dir / "remove_test.jsonl"

    # Create chunks for multiple documents
    chunks = [
        ChunkMetadata(
            chunk_id="doc1_chunk1",
            document_id="doc1",
            content="Doc1 Chunk 1",
            token_count=10,
            section_heading="§1",
            absolute_address="LOV/2024/§1",
            split_reason="none",
        ),
        ChunkMetadata(
            chunk_id="doc1_chunk2",
            document_id="doc1",
            content="Doc1 Chunk 2",
            token_count=15,
            section_heading="§2",
            absolute_address="LOV/2024/§2",
            split_reason="none",
        ),
        ChunkMetadata(
            chunk_id="doc2_chunk1",
            document_id="doc2",
            content="Doc2 Chunk 1",
            token_count=12,
            section_heading="§1",
            absolute_address="LOV/2025/§1",
            split_reason="none",
        ),
        ChunkMetadata(
            chunk_id="doc3_chunk1",
            document_id="doc3",
            content="Doc3 Chunk 1",
            token_count=8,
            section_heading="§1",
            absolute_address="LOV/2026/§1",
            split_reason="none",
        ),
    ]

    # Write all chunks
    with ChunkWriter(output_path) as writer:
        writer.write_chunks(chunks)

    assert writer.chunks_written == 4

    # Remove chunks for doc1
    writer = ChunkWriter(output_path)
    removed_count = writer.remove_chunks_for_document("doc1")

    assert removed_count == 2

    # Verify remaining chunks
    remaining_chunks = []
    with open(output_path, encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            remaining_chunks.append(data["document_id"])

    assert len(remaining_chunks) == 2
    assert "doc1" not in remaining_chunks
    assert "doc2" in remaining_chunks
    assert "doc3" in remaining_chunks


def test_remove_chunks_nonexistent_document(temp_output_dir):
    """Test removing chunks for a document that doesn't exist."""
    output_path = temp_output_dir / "remove_nonexistent.jsonl"

    chunks = [
        ChunkMetadata(
            chunk_id="doc1_chunk1",
            document_id="doc1",
            content="Content",
            token_count=10,
            section_heading="§1",
            absolute_address="LOV/2024/§1",
            split_reason="none",
        ),
    ]

    with ChunkWriter(output_path) as writer:
        writer.write_chunks(chunks)

    # Try to remove chunks for non-existent document
    writer = ChunkWriter(output_path)
    removed_count = writer.remove_chunks_for_document("nonexistent_doc")

    assert removed_count == 0

    # Original chunk should still be there
    with open(output_path, encoding="utf-8") as f:
        line_count = sum(1 for _ in f)
    assert line_count == 1


def test_remove_chunks_from_empty_file(temp_output_dir):
    """Test removing chunks from a non-existent file."""
    output_path = temp_output_dir / "nonexistent.jsonl"

    writer = ChunkWriter(output_path)
    removed_count = writer.remove_chunks_for_document("doc1")

    assert removed_count == 0
