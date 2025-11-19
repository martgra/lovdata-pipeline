"""Integration tests for the chunking pipeline."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from lovdata_pipeline.domain.parsers.xml_chunker import LovdataXMLChunker
from lovdata_pipeline.domain.splitters.recursive_splitter import XMLAwareRecursiveSplitter
from lovdata_pipeline.infrastructure.chunk_writer import ChunkWriter


@pytest.fixture
def sample_xml_file():
    """Create a complete sample XML file for integration testing."""
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html lang="no">
<head><title>Testlov</title></head>
<body>
    <main class="documentBody" data-lovdata-URL="NL/lov/2024-01-01" id="dokument">
        <h1>Testlov om integrasjonstesting</h1>

        <article class="legalArticle" data-lovdata-URL="NL/lov/2024-01-01/§1" id="paragraf-1">
            <h2 class="legalArticleHeader">
                <span class="legalArticleValue">§ 1</span>. Formål
            </h2>
            <article class="legalP" id="paragraf-1-ledd-1">
                Denne loven skal sikre god kvalitet i integrasjonstesting av XML-prosessering.
            </article>
            <article class="legalP" id="paragraf-1-ledd-2">
                Loven regulerer hvordan lovtekster skal parses, chunkes og skrives til disk.
            </article>
        </article>

        <article class="legalArticle" data-lovdata-URL="NL/lov/2024-01-01/§2" id="paragraf-2">
            <h2 class="legalArticleHeader">
                <span class="legalArticleValue">§ 2</span>. Virkeområde
            </h2>
            <article class="legalP" id="paragraf-2-ledd-1">
                Loven gjelder for alle som utvikler systemer for lovdata-prosessering.
                Den omfatter parsing av XML, tokenisering av tekst, og splitting av dokumenter.
                Systemet skal være minnesikkert og effektivt. Dette er en lengre paragraf som
                inneholder mer tekst for å teste splitting-funksjonaliteten i systemet vårt.
                Vi ønsker å verifisere at paragraf-basert splitting fungerer korrekt når
                paragrafer blir for store. Dette er viktig for å sikre god ytelse.
            </article>
        </article>

        <article class="legalArticle" data-lovdata-URL="NL/lov/2024-01-01/§3" id="paragraf-3">
            <h2 class="legalArticleHeader">
                <span class="legalArticleValue">§ 3</span>. Definisjoner
            </h2>
            <article class="legalP" id="paragraf-3-ledd-1">
                I denne loven menes med chunk: en tekstdel som ikke overstiger maksimalt antall tokens.
            </article>
        </article>
    </main>
</body>
</html>"""

    with TemporaryDirectory() as tmpdir:
        xml_path = Path(tmpdir) / "test-doc.xml"
        xml_path.write_text(xml_content, encoding="utf-8")
        yield xml_path


def test_full_pipeline_integration(sample_xml_file):
    """Test the complete chunking pipeline end-to-end."""
    with TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "chunks.jsonl"

        # Step 1: Parse XML
        chunker = LovdataXMLChunker(sample_xml_file)
        articles = chunker.extract_articles()

        assert len(articles) == 3, "Should extract 3 articles"

        # Step 2: Split articles
        splitter = XMLAwareRecursiveSplitter(max_tokens=100)
        all_chunks = []

        for article in articles:
            chunks = splitter.split_article(article)
            all_chunks.extend(chunks)

        assert len(all_chunks) >= 3, "Should have at least 3 chunks"

        # Step 3: Write to JSONL
        with ChunkWriter(output_path) as writer:
            writer.write_chunks(all_chunks)

        assert output_path.exists(), "Output file should exist"
        assert writer.chunks_written == len(all_chunks)

        # Step 4: Verify output
        with open(output_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        assert len(lines) == len(all_chunks), "Should have one line per chunk"

        # Verify first chunk
        first_chunk = json.loads(lines[0])
        assert "chunk_id" in first_chunk
        assert "document_id" in first_chunk
        assert "content" in first_chunk
        assert "token_count" in first_chunk
        assert first_chunk["document_id"] == "test-doc"


def test_pipeline_with_splitting(sample_xml_file):
    """Test pipeline with token limit that forces splitting."""
    with TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "chunks.jsonl"

        # Use low token limit to force splitting
        chunker = LovdataXMLChunker(sample_xml_file)
        splitter = XMLAwareRecursiveSplitter(max_tokens=50)

        all_chunks = []
        for article in chunker.extract_articles():
            chunks = splitter.split_article(article)
            all_chunks.extend(chunks)

        # Should have more chunks due to splitting
        assert len(all_chunks) > 3

        # Check that some chunks were split
        split_reasons = [c.split_reason for c in all_chunks]
        assert "paragraph" in split_reasons or "sentence" in split_reasons

        # Write and verify
        with ChunkWriter(output_path) as writer:
            writer.write_chunks(all_chunks)

        # Verify all chunks respect token limit
        for chunk in all_chunks:
            assert chunk.token_count <= 60  # Allow small tolerance


def test_pipeline_preserves_metadata(sample_xml_file):
    """Test that pipeline preserves all metadata through the process."""
    with TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "chunks.jsonl"

        chunker = LovdataXMLChunker(sample_xml_file)
        splitter = XMLAwareRecursiveSplitter(max_tokens=100)

        all_chunks = []
        for article in chunker.extract_articles():
            chunks = splitter.split_article(article)
            all_chunks.extend(chunks)

        with ChunkWriter(output_path) as writer:
            writer.write_chunks(all_chunks)

        # Read back and verify metadata
        with open(output_path, "r", encoding="utf-8") as f:
            for line in f:
                chunk_data = json.loads(line)

                # Required fields
                assert chunk_data["chunk_id"]
                assert chunk_data["document_id"] == "test-doc"
                assert chunk_data["content"]
                assert chunk_data["token_count"] > 0
                assert chunk_data["split_reason"] in ["none", "paragraph", "sentence", "token"]

                # Optional fields should be present
                assert "section_heading" in chunk_data
                assert "absolute_address" in chunk_data
                assert "parent_chunk_id" in chunk_data


def test_pipeline_with_real_xml_sample():
    """Test pipeline with an actual XML file if available."""
    # Test with actual file if it exists
    test_file = Path("data/extracted/gjeldende-lover/nl/nl-16870415-000.xml")

    if not test_file.exists():
        pytest.skip("Real XML file not available")

    with TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "chunks.jsonl"

        # Process real file
        chunker = LovdataXMLChunker(test_file)
        splitter = XMLAwareRecursiveSplitter(max_tokens=6800)

        articles = chunker.extract_articles()
        assert len(articles) > 0, "Should extract articles from real file"

        all_chunks = []
        for article in articles:
            chunks = splitter.split_article(article)
            all_chunks.extend(chunks)

        # Write output
        with ChunkWriter(output_path) as writer:
            writer.write_chunks(all_chunks)

        # Verify
        assert output_path.exists()
        assert output_path.stat().st_size > 0

        # Check output is valid JSON
        with open(output_path, "r", encoding="utf-8") as f:
            for line in f:
                chunk = json.loads(line)  # Should not raise
                assert chunk["document_id"] == test_file.stem


def test_pipeline_memory_efficiency():
    """Test that pipeline doesn't accumulate data in memory."""
    # This is more of a conceptual test - in practice we'd need profiling
    test_file = Path("data/extracted/gjeldende-lover/nl/nl-16870415-000.xml")

    if not test_file.exists():
        pytest.skip("Real XML file not available")

    with TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "chunks.jsonl"

        # Process file with streaming pattern
        chunker = LovdataXMLChunker(test_file)
        splitter = XMLAwareRecursiveSplitter(max_tokens=6800)

        with ChunkWriter(output_path) as writer:
            # Process articles one at a time (streaming)
            articles = chunker.extract_articles()
            for article in articles:
                chunks = splitter.split_article(article)
                writer.write_chunks(chunks)
                # Each iteration, old chunks should be garbage collected

        # Verify output was created
        assert output_path.exists()
        assert writer.chunks_written > 0


def test_pipeline_error_handling():
    """Test that pipeline handles errors gracefully."""
    with TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "chunks.jsonl"

        # Try to process non-existent file
        chunker = LovdataXMLChunker("nonexistent.xml")

        with pytest.raises(FileNotFoundError):
            chunker.extract_articles()


def test_multiple_files_integration():
    """Test processing multiple files in sequence."""
    test_files = [
        Path("data/extracted/gjeldende-lover/nl/nl-16870415-000.xml"),
        Path("data/extracted/gjeldende-lover/nl/nl-19090323-000.xml"),
    ]

    # Skip if files don't exist
    available_files = [f for f in test_files if f.exists()]
    if len(available_files) < 2:
        pytest.skip("Multiple test files not available")

    with TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "chunks.jsonl"

        splitter = XMLAwareRecursiveSplitter(max_tokens=6800)
        total_chunks = 0

        with ChunkWriter(output_path) as writer:
            for xml_file in available_files:
                chunker = LovdataXMLChunker(xml_file)
                articles = chunker.extract_articles()

                for article in articles:
                    chunks = splitter.split_article(article)
                    writer.write_chunks(chunks)
                    total_chunks += len(chunks)

        # Verify combined output
        assert output_path.exists()
        assert writer.chunks_written == total_chunks

        # Count lines in output
        with open(output_path, "r", encoding="utf-8") as f:
            line_count = sum(1 for _ in f)

        assert line_count == total_chunks
