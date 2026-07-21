"""Shared fixtures and helpers."""

import gzip
import json
import random
from pathlib import Path

import pytest

# Anything that steers browser-facing URL construction. Cleared for every test so
# results do not depend on whether pytest happens to run inside a Jupyter kernel.
_ENV_VARS = (
    "JPY_SESSION_NAME",
    "JPY_PARENT_PID",
    "JUPYTERHUB_SERVICE_PREFIX",
    "JPY_BASE_URL",
    "VECTORTILESERVER_CLIENT_PREFIX",
    "VECTORTILESERVER_DISABLE_JUPYTER_LOOPBACK",
)


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    """Run every test outside a Jupyter kernel unless it says otherwise."""
    for var in _ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def write_points(path: Path, count: int = 25, spread: float = 0.01, seed: int = 0) -> Path:
    """Write a GeoJSON FeatureCollection of ``count`` points inside a tiny bbox."""
    rng = random.Random(seed)
    features = [
        {
            "type": "Feature",
            "properties": {"map_code": i % 4},
            "geometry": {
                "type": "Point",
                "coordinates": [rng.uniform(0, spread), rng.uniform(0, spread)],
            },
        }
        for i in range(count)
    ]
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}))
    return path


def count_tile_features(pmtiles_path: Path, z: int, x: int, y: int) -> int:
    """Decode one tile out of a PMTiles archive and count its features."""
    import mapbox_vector_tile
    from pmtiles.reader import MmapSource, Reader

    with open(pmtiles_path, "rb") as f:
        data = Reader(MmapSource(f)).get(z, x, y)

    assert data is not None, f"no tile at {z}/{x}/{y} in {pmtiles_path}"
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)

    return sum(len(layer["features"]) for layer in mapbox_vector_tile.decode(data).values())


def write_minimal_pmtiles(path: Path) -> Path:
    """
    Write a valid single-tile PMTiles archive without shelling out to tippecanoe.

    Lets the server, URL, and bridge tests run on a plain `pip install` — only the
    conversion tests actually need tippecanoe on PATH.
    """
    import mapbox_vector_tile
    from pmtiles.tile import Compression, TileType
    from pmtiles.writer import Writer

    tile = mapbox_vector_tile.encode(
        [
            {
                "name": "points",
                "features": [{"geometry": "POINT(100 200)", "properties": {"map_code": 1}}],
            }
        ]
    )

    with open(path, "wb") as f:
        writer = Writer(f)
        writer.write_tile(0, gzip.compress(tile))
        writer.finalize(
            {
                "tile_type": TileType.MVT,
                "tile_compression": Compression.GZIP,
                "internal_compression": Compression.GZIP,
                "min_zoom": 0,
                "max_zoom": 0,
                "min_lon_e7": 0,
                "min_lat_e7": 0,
                "max_lon_e7": int(0.01 * 1e7),
                "max_lat_e7": int(0.01 * 1e7),
            },
            {"vector_layers": [{"id": "points", "fields": {"map_code": "Number"}}]},
        )

    return path


@pytest.fixture
def pmtiles_file(tmp_path: Path) -> Path:
    """A ready-to-serve PMTiles archive."""
    return write_minimal_pmtiles(tmp_path / "sample.pmtiles")
