"""Integration test for the simplified pipeline.

Tests the complete flow: parse → chunk → embed → index.
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from lovdata_pipeline.domain.services.chunking_service import ChunkingService
from lovdata_pipeline.domain.services.xml_parsing_service import XMLParsingService


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
    parser = XMLParsingService()
    articles = parser.parse_file(sample_xml_file)

    assert len(articles) == 2
    assert articles[0].article_id == "art1"
    assert "Test Article" in articles[0].heading
    assert "test article" in articles[0].content.lower()
    assert articles[0].address == "NL/test/§1"


def test_chunk_article(sample_xml_file):
    """Test chunking a file."""
    chunking_service = ChunkingService(target_tokens=512, max_tokens=1000)

    chunks = chunking_service.chunk_file(
        sample_xml_file, "test-doc", "test-dataset", "test-hash"
    )

    assert len(chunks) > 0
    assert chunks[0].document_id == "test-doc"
    assert chunks[0].dataset_name == "test-dataset"
    assert len(chunks[0].content) > 0


def test_embed_chunks():
    """Test embedding chunks with mocked OpenAI."""
    from lovdata_pipeline.domain.models import ChunkMetadata
    from lovdata_pipeline.domain.services.embedding_service import EmbeddingService
    from lovdata_pipeline.infrastructure.openai_embedding_provider import OpenAIEmbeddingProvider

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

    provider = OpenAIEmbeddingProvider(mock_client, "test-model")
    service = EmbeddingService(provider=provider, batch_size=100)

    enriched = service.embed_chunks(chunks)

    assert len(enriched) == 2
    assert enriched[0].embedding == [0.1, 0.2, 0.3]
    assert enriched[1].embedding == [0.4, 0.5, 0.6]
    assert enriched[0].embedding_model == "test-model"


def test_process_file_success(sample_xml_file, tmp_path):
    """Test processing a complete file."""
    from lovdata_pipeline.domain.services.file_processing_service import FileInfo, FileProcessingService
    from lovdata_pipeline.domain.services.embedding_service import EmbeddingService
    from lovdata_pipeline.infrastructure.openai_embedding_provider import OpenAIEmbeddingProvider
    from lovdata_pipeline.infrastructure.chroma_vector_store import ChromaVectorStoreRepository

    file_info = FileInfo(
        path=sample_xml_file,
        doc_id="test-doc",
        dataset="test-dataset",
        hash="test-hash",
    )

    # Mock ChromaDB collection
    mock_collection = Mock()
    vector_store = ChromaVectorStoreRepository(mock_collection)

    # Mock OpenAI
    mock_client = Mock()
    def mock_embeddings_create(input, model):
        response = Mock()
        response.data = [Mock(embedding=[0.1] * 384) for _ in range(len(input))]
        return response
    mock_client.embeddings.create = mock_embeddings_create

    # Create services (no XMLParsingService needed anymore)
    chunking_service = ChunkingService(target_tokens=512, max_tokens=1000)
    embedding_provider = OpenAIEmbeddingProvider(mock_client, "test-model")
    embedding_service = EmbeddingService(provider=embedding_provider, batch_size=100)

    file_processor = FileProcessingService(
        chunking_service=chunking_service,
        embedding_service=embedding_service,
        vector_store=vector_store,
    )

    result = file_processor.process_file(file_info)

    assert result.success is True
    assert result.chunk_count > 0
    assert result.error_message is None

    # Verify ChromaDB was called
    mock_collection.upsert.assert_called_once()


def test_process_file_handles_errors(tmp_path):
    """Test that process_file handles errors gracefully."""
    from lovdata_pipeline.domain.services.file_processing_service import FileInfo, FileProcessingService
    from lovdata_pipeline.domain.services.embedding_service import EmbeddingService
    from lovdata_pipeline.infrastructure.openai_embedding_provider import OpenAIEmbeddingProvider
    from lovdata_pipeline.infrastructure.chroma_vector_store import ChromaVectorStoreRepository

    # Non-existent file
    file_info = FileInfo(
        path=tmp_path / "nonexistent.xml",
        doc_id="test-doc",
        dataset="test-dataset",
        hash="test-hash",
    )

    mock_collection = Mock()
    mock_client = Mock()
    vector_store = ChromaVectorStoreRepository(mock_collection)

    # Create services (no XMLParsingService needed anymore)
    chunking_service = ChunkingService(target_tokens=512, max_tokens=1000)
    embedding_provider = OpenAIEmbeddingProvider(mock_client, "test-model")
    embedding_service = EmbeddingService(provider=embedding_provider, batch_size=100)

    file_processor = FileProcessingService(
        chunking_service=chunking_service,
        embedding_service=embedding_service,
        vector_store=vector_store,
    )

    result = file_processor.process_file(file_info)

    assert result.success is False
    assert result.chunk_count == 0
    assert result.error_message is not None


def test_process_file_no_articles_fails(tmp_path):
    """Test that files with no extractable articles are marked as failed."""
    from lovdata_pipeline.domain.services.file_processing_service import FileInfo, FileProcessingService
    from lovdata_pipeline.domain.services.embedding_service import EmbeddingService
    from lovdata_pipeline.infrastructure.openai_embedding_provider import OpenAIEmbeddingProvider
    from lovdata_pipeline.infrastructure.chroma_vector_store import ChromaVectorStoreRepository

    # Create an XML file with no extractable articles
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html lang="no">
<head><title>Empty Law</title></head>
<body>
    <main class="documentBody" id="dokument">
        <h1>Law with No Content</h1>
        <article class="changesToParent">
            This is metadata, not a legal article.
        </article>
    </main>
</body>
</html>"""

    xml_file = tmp_path / "empty.xml"
    xml_file.write_text(xml_content, encoding="utf-8")

    file_info = FileInfo(
        path=xml_file,
        doc_id="empty-doc",
        dataset="test-dataset",
        hash="test-hash",
    )

    # Create services (no XMLParsingService needed anymore)
    from lovdata_pipeline.domain.services.chunking_service import ChunkingService

    mock_collection = Mock()
    mock_client = Mock()
    vector_store = ChromaVectorStoreRepository(mock_collection)

    chunking_service = ChunkingService(target_tokens=512, max_tokens=1000)
    embedding_provider = OpenAIEmbeddingProvider(mock_client, "test-model")
    embedding_service = EmbeddingService(provider=embedding_provider, batch_size=100)

    file_processor = FileProcessingService(
        chunking_service=chunking_service,
        embedding_service=embedding_service,
        vector_store=vector_store,
    )

    result = file_processor.process_file(file_info)

    # Should fail when no chunks are generated
    assert result.success is False
    assert result.chunk_count == 0
    assert "No chunks generated" in result.error_message
