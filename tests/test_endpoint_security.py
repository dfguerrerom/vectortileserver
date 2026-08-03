"""The tile endpoint is reachable by any user of an app that mounts it, and
`filePath` is client-supplied, so containment alone is not enough."""

import httpx
import pytest

from vectortileserver.client import TileClient


@pytest.fixture
def secret_file(pmtiles_file):
    secret = pmtiles_file.parent / "secret.json"
    secret.write_text('{"token": "shh"}')
    return secret


@pytest.fixture
def server_url(pmtiles_file):
    client = TileClient(pmtiles_file, allowed_directories=[pmtiles_file.parent])
    return client.server_url


def test_a_non_pmtiles_file_in_an_allowed_directory_is_refused(server_url, secret_file):
    response = httpx.get(f"{server_url}/pmtiles", params={"filePath": str(secret_file)})

    assert response.status_code == 403
    assert "shh" not in response.text


def test_a_pmtiles_file_in_an_allowed_directory_is_still_served(server_url, pmtiles_file):
    response = httpx.get(f"{server_url}/pmtiles", params={"filePath": str(pmtiles_file)})

    assert response.status_code == 200
