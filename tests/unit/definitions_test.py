"""Test Dagster definitions."""

from dagster import build_asset_context

from lovdata_pipeline.definitions import assets, defs, resources


def test_definitions_load():
    """Test that Dagster definitions load without errors."""
    assert defs is not None
    assert len(assets) == 4  # lovdata_sync, changed_file_paths, removed_file_metadata, legal_document_chunks
    assert "lovlig" in resources


def test_lovlig_resource_config():
    """Test that lovlig resource is configured correctly."""
    lovlig_resource = resources["lovlig"]
    # Dataset filter can be configured via env var, just verify it's a string
    assert isinstance(lovlig_resource.dataset_filter, str)
    assert lovlig_resource.max_download_concurrency >= 1


def test_assets_are_registered():
    """Test that all expected assets are registered."""
    asset_names = {asset.key.to_user_string() for asset in assets}
    assert "lovdata_sync" in asset_names
    assert "changed_file_paths" in asset_names
    assert "removed_file_metadata" in asset_names
