"""HTTP range-request behavior of the local tile server.

Needs a real PMTiles file; set PYVECTORTILES_TEST_PMTILES to its path to run:

    PYVECTORTILES_TEST_PMTILES=~/data/some.pmtiles pytest tests/test_range_request.py

Skipped otherwise (e.g. in CI).
"""

import os
from pathlib import Path

import httpx
import pytest

_PMTILES = os.environ.get("PYVECTORTILES_TEST_PMTILES", "")

pytestmark = pytest.mark.skipif(
    not (_PMTILES and Path(_PMTILES).expanduser().is_file()),
    reason="PYVECTORTILES_TEST_PMTILES not set to an existing .pmtiles file",
)


def test_range_request_returns_partial_content():
    from pyvectortiles.client import TileClient

    client = TileClient(str(Path(_PMTILES).expanduser()))
    layer = client.create_leaflet_layer()

    response = httpx.get(layer.url, headers={"range": "bytes=0-1023"})

    assert response.status_code == 206
    assert response.headers.get("content-range", "").startswith("bytes ")
    assert len(response.content) == 1024
