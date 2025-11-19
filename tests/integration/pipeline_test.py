"""Integration test for the simplified pipeline.

Tests the complete flow: parse → chunk → embed → index.
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from lovdata_pipeline.pipeline import (
    chunk_article,
    embed_chunks,
    extract_articles_from_xml,
    process_file,
)


@pytest.fixture
def sample_xml_file(tmp_path):
    """Create a sample XML file for testing."""
    xml_file = tmp_path / "test.xml"
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<html>
<body>
    <article class="legalArticle" id="art1" data-lovdata-URL="NL/test/§1">
        <h2 class="legalArticleHeader">§ 1. Test Article</h2>
        <article class="legalP">
            This is a test article with some content to process.
            It should be parsed, chunked, and embedded.
        </article>
    </article>

    <article class="legalArticle" id="art2" data-lovdata-URL="NL/test/§2">
        <h2 class="legalArticleHeader">§ 2. Another Article</h2>
        <article class="legalP">
            This is another article with different content.
            Testing the pipeline integration.
        </article>
    </article>
</body>
</html>"""
    xml_file.write_text(xml_content)
    return xml_file


def test_extract_articles_from_xml(sample_xml_file):
    """Test extracting articles from XML."""
    articles = extract_articles_from_xml(sample_xml_file)

    assert len(articles) == 2
    assert articles[0]["id"] == "art1"
    assert "Test Article" in articles[0]["heading"]
    assert "test article" in articles[0]["content"].lower()
    assert articles[0]["address"] == "NL/test/§1"


def test_chunk_article():
    """Test chunking an article."""
    article = {
        "id": "test-art",
        "content": "This is test content",
        "heading": "Test Heading",
        "address": "NL/test/§1",
    }

    chunks = chunk_article(article, "test-doc", "test-dataset", max_tokens=1000)

    assert len(chunks) > 0
    assert chunks[0].document_id == "test-doc"
    assert chunks[0].dataset_name == "test-dataset"
    assert "test content" in chunks[0].content.lower()


def test_embed_chunks():
    """Test embedding chunks with mocked OpenAI."""
    from lovdata_pipeline.domain.models import ChunkMetadata

    chunks = [
        ChunkMetadata(
            chunk_id="chunk-1",
            document_id="doc-1",
            dataset_name="test",
            content="Test content 1",
            token_count=10,
            section_heading="Test",
            absolute_address="",
            split_reason="none",
        ),
        ChunkMetadata(
            chunk_id="chunk-2",
            document_id="doc-1",
            dataset_name="test",
            content="Test content 2",
            token_count=10,
            section_heading="Test",
            absolute_address="",
            split_reason="none",
        ),
    ]

    # Mock OpenAI
    mock_client = Mock()
    mock_response = Mock()
    mock_response.data = [
        Mock(embedding=[0.1, 0.2, 0.3]),
        Mock(embedding=[0.4, 0.5, 0.6]),
    ]
    mock_client.embeddings.create.return_value = mock_response

    enriched = embed_chunks(chunks, mock_client, "test-model")

    assert len(enriched) == 2
    assert enriched[0].embedding == [0.1, 0.2, 0.3]
    assert enriched[1].embedding == [0.4, 0.5, 0.6]
    assert enriched[0].embedding_model == "test-model"


def test_process_file_success(sample_xml_file, tmp_path):
    """Test processing a complete file."""
    file_info = {
        "doc_id": "test-doc",
        "path": sample_xml_file,
        "hash": "test-hash",
        "dataset": "test-dataset",
    }

    # Mock ChromaDB collection
    mock_collection = Mock()

    # Mock OpenAI - need to return embeddings for actual chunk count
    # The sample XML will produce ~2 chunks
    mock_client = Mock()

    def mock_embeddings_create(input, model):
        # Return embeddings matching input count
        response = Mock()
        response.data = [Mock(embedding=[0.1] * 384) for _ in range(len(input))]
        return response

    mock_client.embeddings.create = mock_embeddings_create

    config = {
        "chunk_max_tokens": 1000,
        "embedding_model": "test-model",
    }

    success, chunk_count, error = process_file(
        file_info, mock_collection, mock_client, config
    )

    assert success is True
    assert chunk_count > 0
    assert error is None

    # Verify ChromaDB was called
    mock_collection.upsert.assert_called_once()


def test_process_file_handles_errors(tmp_path):
    """Test that process_file handles errors gracefully."""
    # Non-existent file
    file_info = {
        "doc_id": "test-doc",
        "path": tmp_path / "nonexistent.xml",
        "hash": "test-hash",
        "dataset": "test-dataset",
    }

    mock_collection = Mock()
    mock_client = Mock()

    success, chunk_count, error = process_file(
        file_info, mock_collection, {}, config={"chunk_max_tokens": 1000}
    )

    assert success is False
    assert chunk_count == 0
    assert error is not None
