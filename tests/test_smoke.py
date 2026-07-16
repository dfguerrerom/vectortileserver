"""Smoke tests: the package installs, imports, and exposes its entry point."""

import pyvectortiles


def test_version_is_set():
    assert isinstance(pyvectortiles.__version__, str)
    assert pyvectortiles.__version__


def test_tile_client_importable():
    from pyvectortiles.client import TileClient

    assert TileClient is not None
