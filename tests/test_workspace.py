import asyncio
import threading

from vectortileserver.archive import TileArchive
from vectortileserver.pmtiles_layer import VectorTileLayer
from vectortileserver.styles import single_symbol_style
from vectortileserver.workspace import TileWorkspace, default_workspace
from vectortileserver.workspace import open as ws_open


def test_open_returns_an_archive_bound_to_the_workspace(pmtiles_file):
    ws = TileWorkspace(allowed_directories=[pmtiles_file.parent])
    archive = ws.open(pmtiles_file)
    client = next(iter(ws._clients.values()))
    assert isinstance(archive, TileArchive)
    assert archive.workspace is ws
    assert archive.client is client
    assert archive.url == client.pmtiles_url
    assert archive.layers == ("points",)
    assert archive.list_layers() == ["points"]
    assert archive.bounds == [[0.0, 0.0], [0.01, 0.01]]
    assert archive.center == (0.005, 0.005)
    assert archive.source == pmtiles_file
    assert archive.pmtiles_path == pmtiles_file


def test_open_bridges_the_port_before_handing_out_the_url(pmtiles_file, monkeypatch):
    # A MapLibre frontend fetches `url` itself; without the bridge it is
    # unreachable from Voila / SEPAL webviews.
    bridged = []
    monkeypatch.setattr(
        "vectortileserver.client.enable_for_port",
        lambda port, *, path_prefix=None: bridged.append(port),
    )
    ws = TileWorkspace(allowed_directories=[pmtiles_file.parent])

    ws.open(pmtiles_file)
    asyncio.run(ws.open_async(pmtiles_file))

    assert bridged == [ws.port, ws.port]


def test_archive_builds_a_leaflet_layer_on_request(pmtiles_file):
    ws = TileWorkspace(allowed_directories=[pmtiles_file.parent])
    archive = ws.open(pmtiles_file)

    layer = archive.create_leaflet_layer(style=single_symbol_style(color="#abcdef"))

    assert isinstance(layer, VectorTileLayer)
    assert layer.workspace is ws
    assert layer.url == archive.url
    assert layer.bounds == archive.bounds
    fills = [layer_ for layer_ in layer.style["layers"] if layer_["type"] == "fill"]
    assert fills and fills[0]["paint"]["fill-color"] == "#abcdef"


def test_archive_leaflet_layer_honours_layers_to_show(pmtiles_file):
    archive = TileWorkspace(allowed_directories=[pmtiles_file.parent]).open(pmtiles_file)
    layer = archive.create_leaflet_layer(layers_to_show=["points"])
    assert {layer_["source-layer"] for layer_ in layer.style["layers"]} == {"points"}


def test_reopening_same_source_reuses_one_client(pmtiles_file):
    ws = TileWorkspace(allowed_directories=[pmtiles_file.parent])
    ws.open(pmtiles_file)
    ws.open(pmtiles_file)
    assert len(ws._clients) == 1


def test_bounds_unions_all_registered_archives(pmtiles_file, tmp_path):
    from conftest import write_minimal_pmtiles

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


def test_open_async_returns_a_ready_archive(pmtiles_file):
    ws = TileWorkspace(allowed_directories=[pmtiles_file.parent])
    archive = asyncio.run(ws.open_async(pmtiles_file))
    assert isinstance(archive, TileArchive)
    assert archive.workspace is ws
    assert archive.bounds == [[0.0, 0.0], [0.01, 0.01]]


def test_open_many_loads_every_source(pmtiles_file, tmp_path):
    from conftest import write_minimal_pmtiles

    second = write_minimal_pmtiles(tmp_path / "second.pmtiles")
    ws = TileWorkspace(allowed_directories=[pmtiles_file.parent, tmp_path])
    archives = asyncio.run(ws.open_many([pmtiles_file, second]))
    assert len(archives) == 2
    assert all(isinstance(archive, TileArchive) for archive in archives)
    assert archives[0].url != archives[1].url


def test_default_workspace_is_a_singleton():
    assert default_workspace() is default_workspace()


def test_module_open_uses_the_default_workspace(pmtiles_file):
    archive = ws_open(pmtiles_file)
    assert archive.workspace is default_workspace()
    assert archive.bounds == [[0.0, 0.0], [0.01, 0.01]]
