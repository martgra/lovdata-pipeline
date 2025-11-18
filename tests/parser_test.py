"""Tests for the LovdataXMLParser."""

from pathlib import Path

import pytest

from lovdata_pipeline.parsers import LegalChunk, LovdataXMLParser


def test_parser_initialization():
    """Test parser initialization with valid chunk level."""
    parser = LovdataXMLParser(chunk_level="legalArticle")
    assert parser.chunk_level == "legalArticle"


def test_parser_invalid_chunk_level():
    """Test parser raises error for invalid chunk level."""
    with pytest.raises(ValueError, match="Unsupported chunk_level"):
        LovdataXMLParser(chunk_level="invalid")


def test_parse_document(sample_xml_path: Path):
    """Test parsing a sample XML document.

    Args:
        sample_xml_path: Path to sample XML file fixture
    """
    parser = LovdataXMLParser(chunk_level="legalArticle")
    chunks = parser.parse_document(sample_xml_path)

    # Should extract 2 legalArticle elements
    assert len(chunks) == 2

    # Check first chunk
    first_chunk = chunks[0]
    assert isinstance(first_chunk, LegalChunk)
    assert "§ 1" in first_chunk.content
    assert "personopplysninger" in first_chunk.content.lower()
    assert first_chunk.metadata["chunk_type"] == "legalArticle"
    assert first_chunk.metadata["document_type"] == "unknown"


def test_parse_document_file_not_found():
    """Test parser raises error for non-existent file."""
    parser = LovdataXMLParser(chunk_level="legalArticle")

    with pytest.raises(FileNotFoundError):
        parser.parse_document("nonexistent.xml")


def test_chunk_metadata(sample_xml_path: Path):
    """Test that chunks contain expected metadata.

    Args:
        sample_xml_path: Path to sample XML file fixture
    """
    parser = LovdataXMLParser(chunk_level="legalArticle")
    chunks = parser.parse_document(sample_xml_path)

    chunk = chunks[0]
    metadata = chunk.metadata

    # Check required metadata fields
    assert chunk.chunk_id  # chunk_id exists and is not empty
    assert "chunk_index" in metadata
    assert "chunk_length" in metadata
    assert "chunk_type" in metadata
    assert "absolute_address" in metadata
    assert "document_title" in metadata
    assert "document_id" in metadata
    assert "parsed_at" in metadata


def test_parse_legal_p_level(sample_xml_path: Path):
    """Test parsing at legalP (paragraph) level.

    Args:
        sample_xml_path: Path to sample XML file fixture
    """
    parser = LovdataXMLParser(chunk_level="legalP")
    chunks = parser.parse_document(sample_xml_path)

    # Should extract 3 legalP elements (2 in §1, 1 in §2)
    assert len(chunks) == 3

    # Check that chunks are smaller than article-level
    for chunk in chunks:
        assert chunk.metadata["chunk_type"] == "legalP"
