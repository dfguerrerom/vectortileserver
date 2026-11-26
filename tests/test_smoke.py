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
        "TileArchive",
        "VectorTileLayer",
        "TileWorkspace",
        "default_workspace",
        "open",
        "open_async",
        "open_many",
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


#: Run with the leaflet extra unimportable, as on a plain ``pip install``.
_WITHOUT_LEAFLET = """
import importlib.abc, sys

class _Missing(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name.partition(".")[0] in ("ipyleaflet", "mapbox_vector_tile"):
            raise ModuleNotFoundError(f"No module named {name!r}", name=name)
        return None

sys.meta_path.insert(0, _Missing())

import vectortileserver as vts

def report(value):
    print("RESULT", value)  # the package logger shares stdout

archive = vts.open(sys.argv[1])
try:
    report(archive.url)
    report(archive.list_layers())
    report(archive.bounds)
    for build in (archive.create_leaflet_layer, lambda: vts.VectorTileLayer):
        try:
            build()
        except ImportError as e:
            report(e)
finally:
    vts.default_workspace().stop()
"""


def test_the_converter_and_server_work_without_the_leaflet_extra(pmtiles_file):
    import subprocess

    run = subprocess.run(
        [sys.executable, "-c", _WITHOUT_LEAFLET, str(pmtiles_file)],
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert run.returncode == 0, run.stderr
    results = [line[7:] for line in run.stdout.splitlines() if line.startswith("RESULT ")]
    url, layers, bounds, *errors = results
    assert "/pmtiles?filePath=" in url
    assert layers == "['points']"
    assert bounds == "[[0.0, 0.0], [0.01, 0.01]]"
    assert len(errors) == 2
    assert all("vectortileserver[leaflet]" in e for e in errors)


def test_unknown_attribute_still_raises():
    import vectortileserver as vts

    with pytest.raises(AttributeError):
        vts.does_not_exist
