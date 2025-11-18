"""Test configuration for Lovdata pipeline tests."""

from pathlib import Path
from unittest.mock import Mock

import pytest


@pytest.fixture
def sample_xml_path(tmp_path: Path) -> Path:
    """Create a sample Lovdata XML file for testing.

    Args:
        tmp_path: Pytest temporary directory fixture

    Returns:
        Path to sample XML file
    """
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <title>Test Law</title>
</head>
<body>
    <section class="section" data-absoluteaddress="/kapittel/1/">
        <h1>Kapittel 1. Formål og virkeområde</h1>

        <article class="legalArticle" data-absoluteaddress="/kapittel/1/paragraf/1/" id="paragraf-1">
            <h2>§ 1. Lovens formål</h2>

            <article class="legalP" data-absoluteaddress="/kapittel/1/paragraf/1/ledd/1/">
                Lovens formål er å sikre at behandling av personopplysninger skjer
                i samsvar med grunnleggende personvernhensyn.
            </article>

            <article class="legalP" data-absoluteaddress="/kapittel/1/paragraf/1/ledd/2/">
                Loven skal sikre at personopplysninger behandles i samsvar med
                personvernforordningen.
            </article>
        </article>

        <article class="legalArticle" data-absoluteaddress="/kapittel/1/paragraf/2/" id="paragraf-2">
            <h2>§ 2. Virkeområde</h2>

            <article class="legalP" data-absoluteaddress="/kapittel/1/paragraf/2/ledd/1/">
                Loven gjelder for behandling av personopplysninger som helt eller delvis
                skjer med elektroniske hjelpemidler.
            </article>
        </article>
    </section>
</body>
</html>
"""
    xml_file = tmp_path / "test-law.xml"
    xml_file.write_text(xml_content)
    return xml_file


@pytest.fixture
def mock_lovlig_resource():
    """Create a mock LovligResource for testing.

    Returns:
        Mock LovligResource instance
    """
    from lovdata_pipeline.resources import LovligResource

    resource = Mock(spec=LovligResource)
    resource.dataset_filter = "gjeldende"
    resource.raw_data_dir = "./data/raw"
    resource.extracted_data_dir = "./data/extracted"
    resource.state_file = "./data/state.json"

    return resource


@pytest.fixture
def mock_chromadb_resource():
    """Create a mock ChromaDBResource for testing.

    Returns:
        Mock ChromaDBResource instance
    """
    from lovdata_pipeline.resources import ChromaDBResource

    resource = Mock(spec=ChromaDBResource)
    resource.persist_directory = "./data/chromadb"
    resource.collection_name = "test_collection"
    resource.distance_metric = "cosine"

    return resource
