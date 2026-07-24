from vectortileserver import TileClient
from vectortileserver.pmtiles_layer import VectorTileLayer
from vectortileserver.styles import single_symbol_style


def test_create_leaflet_layer_returns_bounded_vector_tile_layer(pmtiles_file):
    client = TileClient(pmtiles_file, allowed_directories=[pmtiles_file.parent])
    layer = client.create_leaflet_layer()
    assert isinstance(layer, VectorTileLayer)
    assert layer.bounds == [[0.0, 0.0], [0.01, 0.01]]  # from write_minimal_pmtiles header
    assert layer.list_layers() == ["points"]
    assert layer.source == pmtiles_file


def test_create_leaflet_layer_accepts_a_style_builder(pmtiles_file):
    client = TileClient(pmtiles_file, allowed_directories=[pmtiles_file.parent])
    layer = client.create_leaflet_layer(style=single_symbol_style(color="#abcdef"))
    fills = [layer_ for layer_ in layer.style["layers"] if layer_["type"] == "fill"]
    assert fills and fills[0]["paint"]["fill-color"] == "#abcdef"


def test_create_leaflet_layer_filters_custom_style_missing_source_layer(pmtiles_file):
    client = TileClient(pmtiles_file, allowed_directories=[pmtiles_file.parent])
    custom_style = {
        "version": 8,
        "sources": {},
        "layers": [
            {"id": "a", "type": "fill", "source-layer": "points"},
            {"id": "b", "type": "background"},
        ],
    }
    layer = client.create_leaflet_layer(style=custom_style, layers_to_show=["points"])
    assert [layer_["id"] for layer_ in layer.style["layers"]] == ["a"]
