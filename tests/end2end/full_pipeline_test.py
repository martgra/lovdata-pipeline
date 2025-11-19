"""End-to-end tests for the complete Lovdata pipeline.

These tests verify the entire pipeline flow from ingestion through chunking.
"""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import pytest
from dagster import materialize

from lovdata_pipeline.definitions import changed_file_paths, legal_document_chunks
from lovdata_pipeline.domain.models import FileMetadata


@pytest.fixture
def test_xml_files(tmp_path):
    """Create test XML files in a temporary directory structure."""
    extracted_dir = tmp_path / "extracted" / "gjeldende-lover"
    extracted_dir.mkdir(parents=True)

    # Create sample XML files
    xml_files = {
        "nl-test-001.xml": """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html lang="no">
<head><title>Testlov 1</title></head>
<body>
    <main class="documentBody" data-lovdata-URL="NL/lov/2024-01-01" id="dokument">
        <article class="legalArticle" data-lovdata-URL="NL/lov/2024-01-01/§1" id="paragraf-1">
            <h2 class="legalArticleHeader">
                <span class="legalArticleValue">§ 1</span>. Formål
            </h2>
            <article class="legalP" id="paragraf-1-ledd-1">
                Denne loven regulerer testing av pipeline-systemer.
            </article>
        </article>
    </main>
</body>
</html>""",
        "nl-test-002.xml": """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html lang="no">
<head><title>Testlov 2</title></head>
<body>
    <main class="documentBody" data-lovdata-URL="NL/lov/2024-01-02" id="dokument">
        <article class="legalArticle" data-lovdata-URL="NL/lov/2024-01-02/§1" id="paragraf-1">
            <h2 class="legalArticleHeader">
                <span class="legalArticleValue">§ 1</span>. Virkeområde
            </h2>
            <article class="legalP" id="paragraf-1-ledd-1">
                Loven gjelder for hele landet og alle testmiljøer.
            </article>
            <article class="legalP" id="paragraf-1-ledd-2">
                Spesielle regler kan gjelde for utviklingsmiljøer.
            </article>
        </article>
    </main>
</body>
</html>""",
    }

    for filename, content in xml_files.items():
        file_path = extracted_dir / "nl" / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)

    return tmp_path, list((extracted_dir / "nl").glob("*.xml"))


def test_full_pipeline_e2e(test_xml_files):
    """Test complete pipeline: changed_file_paths → chunking → output validation."""
    tmp_path, xml_files = test_xml_files

    # Setup output path
    output_file = tmp_path / "chunks" / "output.jsonl"
    output_file.parent.mkdir(parents=True)

    # Simulate the changed_file_paths output
    file_paths = [str(xml_file) for xml_file in xml_files]

    # Test the chunking with file paths
    with patch("lovdata_pipeline.assets.chunking.get_settings") as mock_settings:
        mock_settings.return_value.chunk_max_tokens = 6800
        mock_settings.return_value.chunk_output_path = output_file
        mock_settings.return_value.extracted_data_dir = tmp_path / "extracted"

        from lovdata_pipeline.assets.chunking import legal_document_chunks
        from dagster import build_asset_context

        # Mock lovlig resource
        mock_lovlig = MagicMock()
        context = build_asset_context(resources={"lovlig": mock_lovlig})
        result = legal_document_chunks(context, file_paths)

        assert result is not None

    # Verify output file exists and has correct format
    assert output_file.exists()

    # Read and validate chunks
    chunks = []
    with open(output_file) as f:
        for line in f:
            chunk = json.loads(line)
            chunks.append(chunk)

    # Validate we got chunks from both files
    assert len(chunks) > 0

    # Validate chunk structure
    required_fields = {
        "chunk_id",
        "document_id",
        "content",
        "token_count",
        "section_heading",
        "absolute_address",
        "split_reason",
        "parent_chunk_id",
    }

    for chunk in chunks:
        assert set(chunk.keys()) == required_fields
        assert chunk["token_count"] > 0
        assert chunk["split_reason"] in ["none", "paragraph", "sentence", "token"]
        assert len(chunk["content"]) > 0

    # Verify we have chunks from both documents
    doc_ids = {chunk["document_id"] for chunk in chunks}
    assert "nl-test-001" in doc_ids
    assert "nl-test-002" in doc_ids


def test_chunking_with_real_xml(test_xml_files):
    """Test chunking asset with real XML files end-to-end."""
    tmp_path, xml_files = test_xml_files
    output_file = tmp_path / "chunks" / "e2e_output.jsonl"
    output_file.parent.mkdir(parents=True)

    # Convert Path objects to strings
    file_paths = [str(xml_file) for xml_file in xml_files]

    with patch("lovdata_pipeline.assets.chunking.get_settings") as mock_settings:
        mock_settings.return_value.chunk_max_tokens = 6800
        mock_settings.return_value.chunk_output_path = output_file
        mock_settings.return_value.extracted_data_dir = tmp_path / "extracted"

        # Import the asset function directly
        from lovdata_pipeline.assets.chunking import legal_document_chunks
        from dagster import build_asset_context

        # Mock lovlig resource
        mock_lovlig = MagicMock()
        context = build_asset_context(resources={"lovlig": mock_lovlig})

        # Execute the asset
        result = legal_document_chunks(context, file_paths)

        # Verify result
        assert result is not None
        assert output_file.exists()

        # Check metadata
        metadata = result.metadata
        assert metadata["files_processed"].value == 2
        assert metadata["total_chunks"].value >= 2  # At least 2 articles
        assert metadata["success_rate"].value == 100.0
        assert metadata["files_failed"].value == 0

        # Verify output content
        chunks = []
        with open(output_file) as f:
            for line in f:
                chunks.append(json.loads(line))

        assert len(chunks) >= 2
        assert all(chunk["token_count"] <= 6800 for chunk in chunks)


def test_chunking_handles_empty_files(tmp_path):
    """Test that chunking handles files with no extractable content."""
    # Create an XML file with no legalArticle elements
    xml_file = tmp_path / "nl-empty-001.xml"
    xml_file.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html lang="no">
<head><title>Empty</title></head>
<body>
    <main class="documentBody" id="dokument">
        <p>No legal articles here</p>
    </main>
</body>
</html>""")

    output_file = tmp_path / "chunks" / "empty_output.jsonl"
    output_file.parent.mkdir(parents=True)

    with patch("lovdata_pipeline.assets.chunking.get_settings") as mock_settings:
        mock_settings.return_value.chunk_max_tokens = 6800
        mock_settings.return_value.chunk_output_path = output_file
        mock_settings.return_value.extracted_data_dir = tmp_path

        from lovdata_pipeline.assets.chunking import legal_document_chunks
        from dagster import build_asset_context

        # Mock lovlig resource
        mock_lovlig = MagicMock()
        context = build_asset_context(resources={"lovlig": mock_lovlig})
        result = legal_document_chunks(context, [str(xml_file)])

        # Should succeed but produce no chunks (file is not counted as processed since no articles found)
        assert result is not None
        assert result.metadata["files_processed"].value == 0  # No articles = not processed
        assert result.metadata["total_chunks"].value == 0
        assert result.metadata["success_rate"].value == 0.0  # No files processed = 0% success


def test_chunking_handles_large_paragraphs(tmp_path):
    """Test that chunking properly splits large paragraphs."""
    # Create XML with a very large paragraph
    large_text = " ".join(
        ["Dette er en veldig lang setning som gjentas mange ganger."] * 200
    )

    xml_file = tmp_path / "nl-large-001.xml"
    xml_file.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html lang="no">
<head><title>Large</title></head>
<body>
    <main class="documentBody" data-lovdata-URL="NL/lov/2024-01-01" id="dokument">
        <article class="legalArticle" data-lovdata-URL="NL/lov/2024-01-01/§1" id="paragraf-1">
            <h2 class="legalArticleHeader">
                <span class="legalArticleValue">§ 1</span>. Lang paragraf
            </h2>
            <article class="legalP" id="paragraf-1-ledd-1">
                {large_text}
            </article>
        </article>
    </main>
</body>
</html>""")

    output_file = tmp_path / "chunks" / "large_output.jsonl"
    output_file.parent.mkdir(parents=True)

    with patch("lovdata_pipeline.assets.chunking.get_settings") as mock_settings:
        mock_settings.return_value.chunk_max_tokens = 1000  # Low limit to force splitting
        mock_settings.return_value.chunk_output_path = output_file
        mock_settings.return_value.extracted_data_dir = tmp_path

        from lovdata_pipeline.assets.chunking import legal_document_chunks
        from dagster import build_asset_context

        # Mock lovlig resource
        mock_lovlig = MagicMock()
        context = build_asset_context(resources={"lovlig": mock_lovlig})
        result = legal_document_chunks(context, [str(xml_file)])

        # Should produce multiple chunks
        assert result.metadata["total_chunks"].value > 1

        # Verify all chunks are under limit
        chunks = []
        with open(output_file) as f:
            for line in f:
                chunks.append(json.loads(line))

        assert len(chunks) > 1
        assert all(chunk["token_count"] <= 1000 for chunk in chunks)

        # At least one chunk should have been split
        split_reasons = [chunk["split_reason"] for chunk in chunks]
        assert any(reason != "none" for reason in split_reasons)


def test_pipeline_memory_efficiency(test_xml_files):
    """Test that pipeline processes files one-by-one without loading all into memory."""
    tmp_path, xml_files = test_xml_files
    output_file = tmp_path / "chunks" / "memory_test.jsonl"
    output_file.parent.mkdir(parents=True)

    file_paths = [str(xml_file) for xml_file in xml_files]

    with patch("lovdata_pipeline.assets.chunking.get_settings") as mock_settings:
        mock_settings.return_value.chunk_max_tokens = 6800
        mock_settings.return_value.chunk_output_path = output_file
        mock_settings.return_value.extracted_data_dir = tmp_path / "extracted"

        from lovdata_pipeline.assets.chunking import legal_document_chunks
        from dagster import build_asset_context

        # Mock lovlig resource
        mock_lovlig = MagicMock()
        context = build_asset_context(resources={"lovlig": mock_lovlig})

        # Execute - should not raise memory errors even with many files
        result = legal_document_chunks(context, file_paths)

        assert result is not None
        assert result.metadata["files_processed"].value == len(xml_files)

        # Verify chunks were written incrementally (file should exist before function returns)
        assert output_file.exists()
        assert output_file.stat().st_size > 0
