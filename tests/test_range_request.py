"""
HTTP range-request behavior of the local tile server.

PMTiles readers fetch archives in byte ranges, so `206` plus a correct
`Content-Range` is the contract everything else rests on. Runs against a
synthetic archive by default; set VECTORTILESERVER_TEST_PMTILES to a real file
to exercise that one instead:

    VECTORTILESERVER_TEST_PMTILES=~/data/some.pmtiles pytest tests/test_range_request.py
"""

import os
from pathlib import Path

import httpx
import pytest

from vectortileserver.client import TileClient


@pytest.fixture
def data_source(pmtiles_file):
    override = os.environ.get("VECTORTILESERVER_TEST_PMTILES", "")
    if override and Path(override).expanduser().is_file():
        return Path(override).expanduser()
    return pmtiles_file


@pytest.fixture
def tile_url(data_source):
    client = TileClient(data_source, allowed_directories=[data_source.parent])
    return client.pmtiles_url


def test_a_range_request_returns_partial_content(tile_url):
    response = httpx.get(tile_url, headers={"range": "bytes=0-127"})

    assert response.status_code == 206
    assert response.headers["content-range"].startswith("bytes 0-127/")
    assert response.headers["accept-ranges"] == "bytes"
    assert len(response.content) == 128


def test_a_request_without_a_range_returns_the_whole_file(tile_url, data_source):
    response = httpx.get(tile_url)

    assert response.status_code == 200
    assert len(response.content) == data_source.stat().st_size


def test_a_range_starting_past_the_end_is_not_satisfiable(tile_url, data_source):
    beyond = data_source.stat().st_size + 10

    response = httpx.get(tile_url, headers={"range": f"bytes={beyond}-"})

    assert response.status_code == 416


def test_a_path_outside_the_allowed_directories_is_refused(tile_url):
    response = httpx.get(tile_url.split("?")[0], params={"filePath": "/etc/passwd"})

    assert response.status_code == 403


def test_there_is_no_shutdown_route(tile_url):
    """
    An unauthenticated kill switch on a loopback port is reachable from any page
    the user happens to have open. It had no callers; keep it that way.
    """
    base = tile_url.split("/pmtiles")[0]

    assert httpx.get(f"{base}/shutdown").status_code == 404
