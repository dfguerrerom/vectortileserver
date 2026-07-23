from vectortileserver.fit import fit, union_bounds
from vectortileserver.pmtiles_layer import VectorTileLayer


class FakeMap:
    def __init__(self, layers):
        self.layers = tuple(layers)
        self.fitted = None

    def fit_bounds(self, bounds):
        self.fitted = bounds


def _layer(bounds_dict):
    return VectorTileLayer._from_archive(
        url="http://x/pmtiles?filePath=/a.pmtiles",
        style={"version": 8, "layers": []},
        metadata={"vector_layers": [], "bounds": bounds_dict},
    )


def test_union_bounds_covers_all_vts_layers():
    m = FakeMap(
        [
            _layer({"left": 0, "bottom": 0, "right": 1, "top": 1}),
            _layer({"left": 2, "bottom": -3, "right": 4, "top": 2}),
            object(),  # a non-vts layer is ignored
        ]
    )
    assert union_bounds(m) == [[-3, 0], [2, 4]]


def test_fit_calls_map_fit_bounds_with_union():
    m = FakeMap([_layer({"left": 0, "bottom": 0, "right": 1, "top": 1})])
    fit(m)
    assert m.fitted == [[0, 0], [1, 1]]


def test_fit_is_a_noop_when_no_bounded_layers():
    m = FakeMap([object()])
    fit(m)
    assert m.fitted is None
