from vectortileserver.pmtiles_layer import VectorTileLayer
from vectortileserver.workspace import TileWorkspace


def test_open_returns_a_layer_bound_to_the_workspace(pmtiles_file):
    ws = TileWorkspace(allowed_directories=[pmtiles_file.parent])
    layer = ws.open(pmtiles_file)
    assert isinstance(layer, VectorTileLayer)
    assert layer.workspace is ws
    assert layer.bounds == [[0.0, 0.0], [0.01, 0.01]]


def test_reopening_same_source_reuses_one_client(pmtiles_file):
    ws = TileWorkspace(allowed_directories=[pmtiles_file.parent])
    ws.open(pmtiles_file)
    ws.open(pmtiles_file)
    assert len(ws._clients) == 1


def test_bounds_unions_all_registered_archives(pmtiles_file, tmp_path):
    from tests.conftest import write_minimal_pmtiles

    second = write_minimal_pmtiles(tmp_path / "second.pmtiles")
    ws = TileWorkspace(allowed_directories=[pmtiles_file.parent, tmp_path])
    ws.open(pmtiles_file)
    ws.open(second)
    assert ws.bounds() == [[0.0, 0.0], [0.01, 0.01]]
