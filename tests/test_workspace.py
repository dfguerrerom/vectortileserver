import threading

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


def test_construction_lock_is_stable_per_key_and_distinct_across_keys(pmtiles_file):
    ws = TileWorkspace(allowed_directories=[pmtiles_file.parent])
    lock_a = ws._construction_lock("key-a")
    lock_a_again = ws._construction_lock("key-a")
    lock_b = ws._construction_lock("key-b")
    assert lock_a is lock_a_again
    assert lock_a is not lock_b


def test_concurrent_open_of_same_source_builds_one_client(pmtiles_file, monkeypatch):
    import vectortileserver.client as client_mod

    builds = []
    real_init = client_mod.TileClient.__init__

    def counting_init(self, *args, **kwargs):
        builds.append(1)
        return real_init(self, *args, **kwargs)

    monkeypatch.setattr(client_mod.TileClient, "__init__", counting_init)

    ws = TileWorkspace(allowed_directories=[pmtiles_file.parent])
    barrier = threading.Barrier(2)
    results = []

    def worker():
        barrier.wait()
        results.append(ws.open(pmtiles_file))

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(builds) == 1  # built exactly once despite two concurrent opens
    assert len(ws._clients) == 1
    assert results[0].url == results[1].url


def test_reopen_with_different_conversion_options_reuses_cached_client(pmtiles_file):
    ws = TileWorkspace(allowed_directories=[pmtiles_file.parent])
    ws.open(pmtiles_file)
    client_before = next(iter(ws._clients.values()))

    ws.open(pmtiles_file, conversion_options={"max_zoom": 5})

    assert len(ws._clients) == 1
    client_after = next(iter(ws._clients.values()))
    assert client_after is client_before
