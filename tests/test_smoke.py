"""Smoke tests: the package installs, imports, and exposes its entry point."""

import vectortileserver


def test_version_is_set():
    assert isinstance(vectortileserver.__version__, str)
    assert vectortileserver.__version__


def test_tile_client_importable():
    import vectortileserver.pmtiles_layer  # noqa: F401  (pulls ipyleaflet, shapely, mvt transitively)
    from vectortileserver.client import TileClient

    assert TileClient is not None
