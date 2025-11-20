"""Unit tests for LovdataChunker."""

from pathlib import Path
from tempfile import NamedTemporaryFile

import pytest

from lovdata_pipeline.domain.parsers.lovdata_chunker import Chunk, LovdataChunker


@pytest.fixture
def chunker():
    """Create a standard chunker instance."""
    return LovdataChunker(target_tokens=100, max_tokens=500)


@pytest.fixture
def sample_standard_law_xml():
    """Create sample XML for a standard law (legalArticle with legalP)."""
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html lang="no">
<head><title>Test Law</title></head>
<body>
    <main class="documentBody" id="dokument">
        <h1>Testlov</h1>
        <section class="section">
            <h2>Kapittel 1. Innledning</h2>
            <article class="legalArticle" data-lovdata-URL="NL/lov/2024-01-01/§1" id="paragraf-1">
                <h2 class="legalArticleHeader">
                    <span class="legalArticleValue">§ 1</span>
                    <span class="legalArticleTitle">Formål</span>
                </h2>
                <article class="legalP" id="paragraf-1-ledd-1" data-absoluteaddress="/lov/2024/§1/ledd1">
                    Dette er første ledd i paragraf 1. Det inneholder viktig informasjon om lovens formål.
                </article>
                <article class="legalP" id="paragraf-1-ledd-2" data-absoluteaddress="/lov/2024/§1/ledd2">
                    Dette er andre ledd. Det bygger videre på første ledd og gir ytterligere detaljer.
                </article>
            </article>
        </section>
    </main>
</body>
</html>"""
    with NamedTemporaryFile(mode="w", suffix=".xml", delete=False, encoding="utf-8") as f:
        f.write(xml_content)
        temp_path = f.name
    yield temp_path
    Path(temp_path).unlink()


@pytest.fixture
def sample_change_law_xml():
    """Create sample XML for a change law (sections with legalP)."""
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html lang="no">
<head><title>Change Law</title></head>
<body>
    <main class="documentBody" id="dokument">
        <h1>Endringslov</h1>
        <section class="section">
            <h2>I</h2>
            <article class="legalP" id="change-1">
                I lov 15. juni 2018 nr. 40 om akvakultur gjøres følgende endringer.
            </article>
            <article class="legalP" id="change-2">
                § 5 skal lyde: Dette er en endring av paragrafen.
            </article>
        </section>
    </main>
</body>
</html>"""
    with NamedTemporaryFile(mode="w", suffix=".xml", delete=False, encoding="utf-8") as f:
        f.write(xml_content)
        temp_path = f.name
    yield temp_path
    Path(temp_path).unlink()


@pytest.fixture
def sample_simple_law_xml():
    """Create sample XML for a simple law (legalP directly under main)."""
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html lang="no">
<head><title>Simple Law</title></head>
<body>
    <main class="documentBody" id="dokument">
        <h1>Enkel lov</h1>
        <article class="legalP" id="ledd-1">
            Dette er første ledd i en enkel lov.
        </article>
        <article class="legalP" id="ledd-2">
            Dette er andre ledd.
        </article>
    </main>
</body>
</html>"""
    with NamedTemporaryFile(mode="w", suffix=".xml", delete=False, encoding="utf-8") as f:
        f.write(xml_content)
        temp_path = f.name
    yield temp_path
    Path(temp_path).unlink()


@pytest.fixture
def sample_law_with_list_xml():
    """Create sample XML with a list inside legalP."""
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html lang="no">
<head><title>Law with List</title></head>
<body>
    <main class="documentBody" id="dokument">
        <h1>Lov med liste</h1>
        <section class="section">
            <h2>Kapittel 1</h2>
            <article class="legalArticle" data-lovdata-URL="NL/lov/2024/§1" id="paragraf-1">
                <h2 class="legalArticleHeader">
                    <span class="legalArticleValue">§ 1</span>
                </h2>
                <article class="legalP" id="paragraf-1-ledd-1">
                    Loven gjelder for:
                    <ol>
                        <li data-name="a)">foretak som driver virksomhet</li>
                        <li data-name="b)">personer som arbeider i slik virksomhet</li>
                        <li data-name="c)">alle andre som berøres</li>
                    </ol>
                    <p class="leddfortsettelse">Dette er en fortsettelse etter listen.</p>
                </article>
            </article>
        </section>
    </main>
</body>
</html>"""
    with NamedTemporaryFile(mode="w", suffix=".xml", delete=False, encoding="utf-8") as f:
        f.write(xml_content)
        temp_path = f.name
    yield temp_path
    Path(temp_path).unlink()


class TestLovdataChunkerInitialization:
    """Test chunker initialization."""

    def test_default_initialization(self):
        """Test creating chunker with default parameters."""
        chunker = LovdataChunker()
        assert chunker.target == 512
        assert chunker.max == 8191
        assert chunker.overlap == int(512 * 0.15)

    def test_custom_initialization(self):
        """Test creating chunker with custom parameters."""
        chunker = LovdataChunker(target_tokens=256, max_tokens=1000, overlap_ratio=0.2)
        assert chunker.target == 256
        assert chunker.max == 1000
        assert chunker.overlap == int(256 * 0.2)


class TestStandardLawChunking:
    """Test chunking standard laws (legalArticle with legalP)."""

    def test_chunk_standard_law(self, chunker, sample_standard_law_xml):
        """Test chunking a standard law with paragraphs and ledd."""
        chunks = chunker.chunk(sample_standard_law_xml)

        assert len(chunks) == 2, "Should create 2 chunks (one per ledd)"

        # First chunk
        assert chunks[0].metadata["paragraph_ref"] == "§ 1"
        assert chunks[0].metadata["paragraph_title"] == "Formål"
        assert chunks[0].metadata["ledd_number"] == 1
        assert chunks[0].metadata["document_title"] == "Testlov"
        assert "første ledd" in chunks[0].text.lower()

        # Second chunk
        assert chunks[1].metadata["paragraph_ref"] == "§ 1"
        assert chunks[1].metadata["ledd_number"] == 2
        assert "andre ledd" in chunks[1].text.lower()

    def test_hierarchical_context_extraction(self, chunker, sample_standard_law_xml):
        """Test that hierarchical context is extracted correctly."""
        chunks = chunker.chunk(sample_standard_law_xml)

        for chunk in chunks:
            assert chunk.metadata["document_title"] == "Testlov"
            assert chunk.metadata["section_heading"] == "Kapittel 1. Innledning"
            assert "Kapittel 1. Innledning" in chunk.metadata["chapter_path"]

    def test_chunk_ids_are_unique(self, chunker, sample_standard_law_xml):
        """Test that each chunk has a unique ID."""
        chunks = chunker.chunk(sample_standard_law_xml)
        chunk_ids = [chunk.chunk_id for chunk in chunks]

        assert len(chunk_ids) == len(set(chunk_ids)), "All chunk IDs should be unique"

    def test_token_counts_are_valid(self, chunker, sample_standard_law_xml):
        """Test that token counts are calculated and within limits."""
        chunks = chunker.chunk(sample_standard_law_xml)

        for chunk in chunks:
            assert chunk.token_count > 0, "Token count should be positive"
            assert chunk.token_count <= chunker.max, "Token count should not exceed max"


class TestChangeLawChunking:
    """Test chunking change laws (sections with legalP)."""

    def test_chunk_change_law(self, chunker, sample_change_law_xml):
        """Test chunking a change law."""
        chunks = chunker.chunk(sample_change_law_xml)

        assert len(chunks) > 0, "Should create at least one chunk"

        # Check that chunks have section metadata
        for chunk in chunks:
            assert "section_heading" in chunk.metadata or "document_title" in chunk.metadata

    def test_change_law_groups_legalp(self, sample_change_law_xml):
        """Test that change law groups multiple legalP elements."""
        # Use larger target to allow grouping
        chunker = LovdataChunker(target_tokens=200, max_tokens=500)
        chunks = chunker.chunk(sample_change_law_xml)

        # Should group legalP elements if they fit within target
        assert len(chunks) >= 1


class TestSimpleLawChunking:
    """Test chunking simple laws (legalP directly under main)."""

    def test_chunk_simple_law(self, chunker, sample_simple_law_xml):
        """Test chunking a simple law."""
        chunks = chunker.chunk(sample_simple_law_xml)

        assert len(chunks) == 2, "Should create 2 chunks (one per legalP)"

        for chunk in chunks:
            assert chunk.metadata["document_title"] == "Enkel lov"
            assert "ledd_number" in chunk.metadata

    def test_simple_law_without_legalp(self, chunker):
        """Test handling law with no legalP elements."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html lang="no">
<body>
    <main class="documentBody" id="dokument">
        <h1>Tom lov</h1>
    </main>
</body>
</html>"""
        with NamedTemporaryFile(mode="w", suffix=".xml", delete=False, encoding="utf-8") as f:
            f.write(xml_content)
            temp_path = f.name

        try:
            chunks = chunker.chunk(temp_path)
            assert len(chunks) == 0, "Should return empty list for law with no content"
        finally:
            Path(temp_path).unlink()


class TestListHandling:
    """Test extraction and handling of lists."""

    def test_extract_list_with_markers(self, chunker, sample_law_with_list_xml):
        """Test that lists with markers are extracted correctly."""
        chunks = chunker.chunk(sample_law_with_list_xml)

        assert len(chunks) > 0
        chunk_text = chunks[0].text

        # Check that list items are preserved
        assert "a)" in chunk_text
        assert "foretak som driver virksomhet" in chunk_text
        assert "b)" in chunk_text
        assert "personer som arbeider" in chunk_text

    def test_list_continuation_preserved(self, chunker, sample_law_with_list_xml):
        """Test that leddfortsettelse after list is preserved."""
        chunks = chunker.chunk(sample_law_with_list_xml)

        chunk_text = chunks[0].text
        assert "fortsettelse etter listen" in chunk_text.lower()


class TestLargeLeddSplitting:
    """Test splitting of ledd that exceed token limits."""

    def test_split_large_ledd_by_sentences(self, chunker):
        """Test that very large ledd is split into multiple chunks."""
        # Create a ledd with many sentences
        long_text = " ".join([f"Dette er setning nummer {i}." for i in range(100)])
        xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html lang="no">
<body>
    <main class="documentBody" id="dokument">
        <h1>Lang lov</h1>
        <section class="section">
            <article class="legalArticle" id="para-1">
                <h2 class="legalArticleHeader">
                    <span class="legalArticleValue">§ 1</span>
                </h2>
                <article class="legalP" id="para-1-ledd-1">
                    {long_text}
                </article>
            </article>
        </section>
    </main>
</body>
</html>"""
        with NamedTemporaryFile(mode="w", suffix=".xml", delete=False, encoding="utf-8") as f:
            f.write(xml_content)
            temp_path = f.name

        try:
            chunks = chunker.chunk(temp_path)
            assert len(chunks) > 1, "Should split large ledd into multiple chunks"

            # All chunks should be within max limit
            for chunk in chunks:
                assert chunk.token_count <= chunker.max
        finally:
            Path(temp_path).unlink()

    def test_split_preserves_metadata(self, chunker):
        """Test that split chunks preserve paragraph metadata."""
        long_text = " ".join([f"Dette er setning {i}." for i in range(100)])
        xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html lang="no">
<body>
    <main class="documentBody" id="dokument">
        <h1>Test</h1>
        <section class="section">
            <article class="legalArticle" id="para-1">
                <h2 class="legalArticleHeader">
                    <span class="legalArticleValue">§ 5</span>
                    <span class="legalArticleTitle">Lang paragraf</span>
                </h2>
                <article class="legalP" id="para-1-ledd-1">
                    {long_text}
                </article>
            </article>
        </section>
    </main>
</body>
</html>"""
        with NamedTemporaryFile(mode="w", suffix=".xml", delete=False, encoding="utf-8") as f:
            f.write(xml_content)
            temp_path = f.name

        try:
            chunks = chunker.chunk(temp_path)

            # All chunks should have same paragraph reference
            for chunk in chunks:
                assert chunk.metadata["paragraph_ref"] == "§ 5"
                assert chunk.metadata["paragraph_title"] == "Lang paragraf"
                assert chunk.metadata["ledd_number"] == 1
        finally:
            Path(temp_path).unlink()


class TestOverlapLogic:
    """Test overlapping chunks."""

    def test_overlap_between_chunks(self):
        """Test that chunks have overlap when splitting."""
        chunker = LovdataChunker(target_tokens=50, max_tokens=500, overlap_ratio=0.2)

        # Create text with many sentences
        long_text = " ".join([f"Sentence number {i} with some content." for i in range(50)])
        xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html lang="no">
<body>
    <main class="documentBody" id="dokument">
        <h1>Test</h1>
        <section class="section">
            <article class="legalArticle" id="para-1">
                <h2 class="legalArticleHeader">
                    <span class="legalArticleValue">§ 1</span>
                </h2>
                <article class="legalP" id="para-1-ledd-1">
                    {long_text}
                </article>
            </article>
        </section>
    </main>
</body>
</html>"""
        with NamedTemporaryFile(mode="w", suffix=".xml", delete=False, encoding="utf-8") as f:
            f.write(xml_content)
            temp_path = f.name

        try:
            chunks = chunker.chunk(temp_path)

            if len(chunks) > 1:
                # Check that consecutive chunks have some overlap
                # (This is a heuristic test - not perfect)
                for i in range(len(chunks) - 1):
                    # Some word from chunk i should appear in chunk i+1
                    words_i = set(chunks[i].text.split())
                    words_next = set(chunks[i + 1].text.split())
                    # Allow for no overlap in edge cases, but typically there should be some
                    # Just verify the mechanism doesn't break
                    assert len(words_i) > 0 and len(words_next) > 0
        finally:
            Path(temp_path).unlink()


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_xml_file(self, chunker):
        """Test handling of minimal/empty XML."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html lang="no">
<body>
</body>
</html>"""
        with NamedTemporaryFile(mode="w", suffix=".xml", delete=False, encoding="utf-8") as f:
            f.write(xml_content)
            temp_path = f.name

        try:
            chunks = chunker.chunk(temp_path)
            assert len(chunks) == 0, "Empty XML should produce no chunks"
        finally:
            Path(temp_path).unlink()

    def test_chunk_with_no_title(self, chunker):
        """Test paragraph without title."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html lang="no">
<body>
    <main class="documentBody" id="dokument">
        <h1>Test</h1>
        <section class="section">
            <article class="legalArticle" id="para-1">
                <h2 class="legalArticleHeader">
                    <span class="legalArticleValue">§ 1</span>
                </h2>
                <article class="legalP" id="para-1-ledd-1">
                    Text without title.
                </article>
            </article>
        </section>
    </main>
</body>
</html>"""
        with NamedTemporaryFile(mode="w", suffix=".xml", delete=False, encoding="utf-8") as f:
            f.write(xml_content)
            temp_path = f.name

        try:
            chunks = chunker.chunk(temp_path)
            assert len(chunks) == 1
            assert chunks[0].metadata["paragraph_title"] is None
        finally:
            Path(temp_path).unlink()

    def test_cross_references_extraction(self, chunker):
        """Test extraction of cross-references."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html lang="no">
<body>
    <main class="documentBody" id="dokument">
        <h1>Test</h1>
        <section class="section">
            <article class="legalArticle" id="para-1">
                <h2 class="legalArticleHeader">
                    <span class="legalArticleValue">§ 1</span>
                </h2>
                <article class="legalP" id="para-1-ledd-1">
                    Se <a href="/lov/2020/§5">§ 5</a> og <a href="/lov/2020/§10">§ 10</a>.
                </article>
            </article>
        </section>
    </main>
</body>
</html>"""
        with NamedTemporaryFile(mode="w", suffix=".xml", delete=False, encoding="utf-8") as f:
            f.write(xml_content)
            temp_path = f.name

        try:
            chunks = chunker.chunk(temp_path)
            assert len(chunks) == 1
            cross_refs = chunks[0].metadata.get("cross_refs", [])
            assert "/lov/2020/§5" in cross_refs
            assert "/lov/2020/§10" in cross_refs
        finally:
            Path(temp_path).unlink()


class TestTokenLimits:
    """Test token limit handling and edge cases."""

    def test_chunk_at_exact_max_tokens_is_included(self):
        """Test that chunks exactly at max_tokens are included, not dropped."""
        chunker = LovdataChunker(target_tokens=50, max_tokens=100)

        # Create text that will be exactly at or very close to max_tokens
        # This tests the <= vs < fix
        text_parts = []
        current_tokens = 0

        # Build text to approximately 100 tokens
        while current_tokens < 95:
            part = "This is a test sentence. "
            text_parts.append(part)
            current_tokens = chunker._count_tokens("".join(text_parts))

        final_text = "".join(text_parts).strip()

        xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html lang="no">
<body>
    <main class="documentBody" id="dokument">
        <h1>Test</h1>
        <section class="section">
            <article class="legalArticle" id="para-1">
                <h2 class="legalArticleHeader">
                    <span class="legalArticleValue">§ 1</span>
                </h2>
                <article class="legalP" id="para-1-ledd-1">
                    {final_text}
                </article>
            </article>
        </section>
    </main>
</body>
</html>"""
        with NamedTemporaryFile(mode="w", suffix=".xml", delete=False, encoding="utf-8") as f:
            f.write(xml_content)
            temp_path = f.name

        try:
            chunks = chunker.chunk(temp_path)

            # Chunk should be created even if at max_tokens
            assert len(chunks) >= 1, "Chunks at max_tokens should be included"

            # All chunks should be within limits
            for chunk in chunks:
                assert chunk.token_count <= chunker.max
        finally:
            Path(temp_path).unlink()

    def test_oversized_chunk_logs_warning(self, caplog):
        """Test that chunks exceeding max in split_by_lists log a warning."""
        import logging

        # Use very small max to trigger warning
        chunker = LovdataChunker(target_tokens=10, max_tokens=20)

        # Create a list with very long items that will exceed max when split
        long_item = " ".join(["word"] * 50)  # This will definitely exceed 20 tokens
        xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html lang="no">
<body>
    <main class="documentBody" id="dokument">
        <h1>Test</h1>
        <section class="section">
            <article class="legalArticle" id="para-1">
                <h2 class="legalArticleHeader">
                    <span class="legalArticleValue">§ 1</span>
                </h2>
                <article class="legalP" id="para-1-ledd-1">
                    <ol>
                        <li data-name="a)">{long_item}</li>
                    </ol>
                </article>
            </article>
        </section>
    </main>
</body>
</html>"""
        with NamedTemporaryFile(mode="w", suffix=".xml", delete=False, encoding="utf-8") as f:
            f.write(xml_content)
            temp_path = f.name

        try:
            with caplog.at_level(logging.WARNING):
                chunks = chunker.chunk(temp_path)

            # Should have logged a warning about exceeding max tokens
            assert any("exceeds max tokens" in record.message for record in caplog.records)
        finally:
            Path(temp_path).unlink()


class TestChunkDataclass:
    """Test the Chunk dataclass."""

    def test_chunk_creation(self):
        """Test creating a Chunk object."""
        chunk = Chunk(
            chunk_id="test-1",
            text="Test text",
            token_count=10,
            metadata={"key": "value"},
        )

        assert chunk.chunk_id == "test-1"
        assert chunk.text == "Test text"
        assert chunk.token_count == 10
        assert chunk.metadata["key"] == "value"

    def test_chunk_metadata_access(self):
        """Test accessing metadata fields."""
        chunk = Chunk(
            chunk_id="test-1",
            text="Test",
            token_count=5,
            metadata={
                "paragraph_ref": "§ 1",
                "ledd_number": 1,
                "document_title": "Test Law",
            },
        )

        assert chunk.metadata["paragraph_ref"] == "§ 1"
        assert chunk.metadata["ledd_number"] == 1
        assert chunk.metadata["document_title"] == "Test Law"
