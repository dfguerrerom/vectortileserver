"""Smoke tests: the package installs, imports, and exposes its entry point."""

import importlib
import sys

import pytest

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


def test_a_bare_import_stays_light():
    """
    `import vectortileserver` (e.g. just to read __version__) must not drag in
    geopandas, ipyleaflet, or shapely. TileClient is exposed lazily to keep it
    cheap.
    """
    import subprocess
    import sys

    heavy = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, vectortileserver;"
            "print([m for m in ('geopandas', 'ipyleaflet', 'shapely') if m in sys.modules])",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    assert heavy.stdout.strip() == "[]"


def test_public_names_are_exposed_lazily():
    import vectortileserver as vts

    for name in (
        "TileClient",
        "VectorTileLayer",
        "TileWorkspace",
        "default_workspace",
        "open",
        "open_async",
        "open_many",
        "fit",
        "union_bounds",
        "default_style",
        "categorized_style",
        "single_symbol_style",
    ):
        assert hasattr(vts, name), name


def test_bare_import_does_not_pull_ipyleaflet():
    for mod in [m for m in sys.modules if m.startswith(("ipyleaflet", "geopandas"))]:
        del sys.modules[mod]
    importlib.reload(importlib.import_module("vectortileserver"))
    assert "ipyleaflet" not in sys.modules
    assert "geopandas" not in sys.modules


def test_unknown_attribute_still_raises():
    import vectortileserver as vts

    with pytest.raises(AttributeError):
        vts.does_not_exist


def _fresh_vts():
    # Only drop the package itself and the submodule under test: clearing
    # every vectortileserver.* submodule (e.g. pmtiles_layer) would force it
    # to reimport and hand back a second, distinct VectorTileLayer class,
    # breaking isinstance checks for other tests sharing this process.
    for mod in ("vectortileserver", "vectortileserver._fit"):
        sys.modules.pop(mod, None)
    return importlib.import_module("vectortileserver")


def test_vts_fit_stays_callable_on_repeated_access():
    vts = _fresh_vts()
    assert callable(vts.fit)
    assert callable(vts.fit)


def test_vts_fit_not_shadowed_by_union_bounds_access():
    vts = _fresh_vts()
    assert callable(vts.union_bounds)
    assert callable(vts.fit)
