"""Smoke tests: the package installs, imports, and exposes its entry point."""

import vectortileserver


def test_version_is_set():
    assert isinstance(vectortileserver.__version__, str)
    assert vectortileserver.__version__


def test_tile_client_importable():
    import vectortileserver.pmtiles_layer  # noqa: F401  (pulls ipyleaflet, shapely, mvt transitively)
    from vectortileserver.client import TileClient

    assert TileClient is not None


def test_tile_client_is_exposed_at_the_top_level():
    from vectortileserver.client import TileClient

    assert vectortileserver.TileClient is TileClient


def test_the_server_extension_does_not_drag_in_the_geo_stack():
    """
    The jupyter-server the extension loads into needs none of geopandas,
    ipyleaflet, or shapely. Importing TileClient eagerly from __init__ would
    put all of it in that process.
    """
    import subprocess
    import sys

    heavy = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, vectortileserver._jupyter;"
            "print([m for m in ('geopandas', 'ipyleaflet', 'shapely') if m in sys.modules])",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    assert heavy.stdout.strip() == "[]"
