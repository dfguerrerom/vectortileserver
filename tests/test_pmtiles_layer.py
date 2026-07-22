from vectortileserver.pmtiles_layer import LeafletPMTilesLayer, VectorTileLayer

URL = "http://x/pmtiles?filePath=/tmp/a.pmtiles"
META = {
    "vector_layers": [{"id": "points", "minzoom": 0, "maxzoom": 14}],
    "bounds": {"left": -1.0, "bottom": -2.0, "right": 3.0, "top": 4.0},
    "center": (1.0, 1.0),
}


def _layer():
    return VectorTileLayer._from_archive(url=URL, style={"version": 8, "layers": []}, metadata=META)


def test_layer_exposes_fit_ready_bounds_and_center():
    layer = _layer()
    assert layer.bounds == [[-2.0, -1.0], [4.0, 3.0]]
    assert layer.center == (1.0, 1.0)


def test_list_layers_reads_vector_layer_ids():
    assert _layer().list_layers() == ["points"]


def test_with_style_returns_new_layer_same_archive_new_style():
    layer = _layer()
    restyled = layer.with_style({"version": 8, "layers": [{"id": "z"}]})
    assert restyled is not layer
    assert restyled.url == layer.url  # same archive
    assert restyled.bounds == layer.bounds  # metadata carried over
    assert restyled.style != layer.style  # new paint


def test_legacy_alias_is_the_same_class():
    assert LeafletPMTilesLayer is VectorTileLayer


def test_pmtiles_path_decodes_from_url():
    assert _layer().pmtiles_path == "/tmp/a.pmtiles"


def test_with_style_preserves_custom_attribution():
    layer = VectorTileLayer._from_archive(
        url=URL,
        style={"version": 8, "layers": []},
        metadata=META,
        attribution="Custom Attribution",
    )
    restyled = layer.with_style({"version": 8, "layers": [{"id": "z"}]})
    assert restyled.attribution == "Custom Attribution"
