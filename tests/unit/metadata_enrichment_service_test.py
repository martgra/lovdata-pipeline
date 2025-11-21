"""Unit tests for MetadataEnrichmentService.

Tests service orchestration and integration. Individual enricher functions are tested via integration tests.
"""

from pathlib import Path
from tempfile import NamedTemporaryFile

import pytest
from lxml import etree

from lovdata_pipeline.domain.services.metadata_enrichment_service import MetadataEnrichmentService


@pytest.fixture
def sample_xml():
    """Create sample XML matching actual Lovdata structure."""
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html lang="no">
<head>
    <title>Lov om arbeidsmiljø (arbeidsmiljøloven)</title>
</head>
<body>
    <header class="documentHeader">
        <dl class="data-document-key-info">
            <dt class="dokid">DokumentID</dt>
            <dd class="dokid">NL/lov/2005-06-17-62</dd>
            <dt class="ministry">Departement</dt>
            <dd class="ministry"><ul><li>Arbeids- og inkluderingsdepartementet</li></ul></dd>
            <dt class="titleShort">Korttittel</dt>
            <dd class="titleShort">arbeidsmiljøloven</dd>
            <dt class="title">Tittel</dt>
            <dd class="title">Lov om arbeidsmiljø, arbeidstid og stillingsvern mv. (arbeidsmiljøloven)</dd>
        </dl>
    </header>
    <main class="documentBody" data-lovdata-URL="NL/lov/2005-06-17-62" id="dokument">
        <h1>Lov om arbeidsmiljø, arbeidstid og stillingsvern mv. (arbeidsmiljøloven)</h1>
        <section class="section" id="kapittel-15">
            <h2>Kapittel 15. Oppsigelse av arbeidsforhold</h2>
            <article class="legalArticle" data-lovdata-URL="NL/lov/2005-06-17-62/§15-11" id="kapittel-15-paragraf-11">
                <h3 class="legalArticleHeader">
                    <span class="legalArticleValue">§ 15-11</span>
                    <span class="legalArticleTitle">Saklig oppsigelse</span>
                </h3>
                <article class="legalP" id="kapittel-15-paragraf-11-ledd-1" data-absoluteaddress="NL/lov/2005-06-17-62/§15-11/ledd1">
                    Oppsigelse skal være saklig begrunnet. Se også
                    <a class="xref" href="lov/1999-07-02-63/§19">§ 19</a> og
                    <a class="xref" href="lov/2005-05-20-28/§4">lov av 20. mai 2005</a>.
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
def xml_tree(sample_xml):
    """Parse sample XML into lxml tree."""
    tree = etree.parse(sample_xml)
    return tree


@pytest.fixture
def xml_root(xml_tree):
    """Get root element from XML tree."""
    return xml_tree.getroot()


@pytest.fixture
def chunk_element(xml_root):
    """Get a specific chunk element from the XML."""
    return xml_root.find('.//article[@class="legalP"][@id="kapittel-15-paragraf-11-ledd-1"]')


@pytest.fixture
def base_chunk_data():
    """Create base chunk data."""
    return {
        "chunk_id": "nl-20050617-062_chunk_0",
        "document_id": "nl-20050617-062",
        "text": "Oppsigelse skal være saklig begrunnet.",
        "token_count": 8,
    }


@pytest.fixture
def service():
    """Create MetadataEnrichmentService instance."""
    return MetadataEnrichmentService()


class TestMetadataEnrichmentService:
    """Tests for MetadataEnrichmentService orchestration."""

    def test_initialization(self, service):
        """Test service initializes with default enrichers."""
        enrichers = service.list_enrichers()
        assert "document_info" in enrichers
        assert "location_info" in enrichers
        assert "hierarchy_info" in enrichers
        assert "references" in enrichers
        assert "section_context" in enrichers

    def test_add_enricher(self, service):
        """Test adding a custom enricher."""
        def custom_enricher(chunk_data, xml_root, chunk_element=None):
            return {"custom_field": "value"}

        service.add_enricher("custom", custom_enricher)
        assert "custom" in service.list_enrichers()

    def test_remove_enricher(self, service):
        """Test removing an enricher."""
        assert "references" in service.list_enrichers()
        result = service.remove_enricher("references")
        assert result is True
        assert "references" not in service.list_enrichers()

    def test_enricher_error_handling(self, service, base_chunk_data, xml_root):
        """Test that enricher errors are caught and logged."""
        def failing_enricher(chunk_data, xml_root, chunk_element=None):
            raise ValueError("Test error")

        service.add_enricher("failing", failing_enricher)

        # Should not raise, should log error and continue
        enriched = service.enrich(base_chunk_data, xml_root)

        # Base data should still be present
        assert enriched["chunk_id"] == base_chunk_data["chunk_id"]

    def test_enricher_order(self, service, base_chunk_data, xml_root):
        """Test enrichers are applied in order."""
        call_order = []

        def enricher1(chunk_data, xml_root, chunk_element=None):
            call_order.append(1)
            return {"field1": 1}

        def enricher2(chunk_data, xml_root, chunk_element=None):
            call_order.append(2)
            return {"field2": 2}

        # Clear defaults and add in specific order
        for name in service.list_enrichers():
            service.remove_enricher(name)

        service.add_enricher("first", enricher1)
        service.add_enricher("second", enricher2)

        service.enrich(base_chunk_data, xml_root)

        assert call_order == [1, 2]

    def test_enrichers_can_override_fields(self, service, base_chunk_data, xml_root):
        """Test that later enrichers can override earlier ones."""
        def enricher1(chunk_data, xml_root, chunk_element=None):
            return {"score": 1}

        def enricher2(chunk_data, xml_root, chunk_element=None):
            return {"score": 2}

        # Clear defaults
        for name in service.list_enrichers():
            service.remove_enricher(name)

        service.add_enricher("first", enricher1)
        service.add_enricher("second", enricher2)

        enriched = service.enrich(base_chunk_data, xml_root)
        assert enriched["score"] == 2


class TestIntegration:
    """Integration tests for complete enrichment pipeline."""

    def test_full_enrichment_pipeline(self, service, base_chunk_data, xml_root, chunk_element):
        """Test complete enrichment pipeline with all enrichers."""
        enriched = service.enrich(base_chunk_data, xml_root, chunk_element)

        # Verify base fields are present
        assert enriched["chunk_id"] == base_chunk_data["chunk_id"]
        assert enriched["document_id"] == base_chunk_data["document_id"]
        assert enriched["text"] == base_chunk_data["text"]
        assert enriched["token_count"] == base_chunk_data["token_count"]

        # Verify enriched fields exist
        assert len(enriched) > len(base_chunk_data)  # Should have added fields
        assert "document_title" in enriched
        assert "absolute_address" in enriched or "chapter_path" in enriched  # At least some metadata

    def test_enrichment_without_chunk_element(self, service, base_chunk_data, xml_root):
        """Test enrichment when chunk_element is None."""
        enriched = service.enrich(base_chunk_data, xml_root, None)

        # Should still work and return base data plus whatever can be extracted
        assert enriched["chunk_id"] == base_chunk_data["chunk_id"]
        assert isinstance(enriched, dict)

    def test_enrichment_idempotency(self, service, base_chunk_data, xml_root, chunk_element):
        """Test that enrichment is idempotent."""
        enriched1 = service.enrich(base_chunk_data, xml_root, chunk_element)
        enriched2 = service.enrich(base_chunk_data, xml_root, chunk_element)

        # Results should be identical
        assert enriched1 == enriched2

    def test_malformed_xml_handling(self, service, base_chunk_data):
        """Test handling of malformed XML."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<html><body><main id="dokument"></main></body></html>"""
        root = etree.fromstring(xml_content.encode())

        # Should not raise, should return base data with what it can extract
        enriched = service.enrich(base_chunk_data, root)

        assert enriched["chunk_id"] == base_chunk_data["chunk_id"]
