from vectortileserver.handler import to_leaflet_bounds, union_bbox_dicts


def test_to_leaflet_bounds_orders_corners_sw_ne():
    b = {"left": -10.0, "bottom": -5.0, "right": 10.0, "top": 5.0}
    assert to_leaflet_bounds(b) == [[-5.0, -10.0], [5.0, 10.0]]


def test_to_leaflet_bounds_none_when_missing_or_partial():
    assert to_leaflet_bounds({}) is None
    assert to_leaflet_bounds({"left": 1, "bottom": 2, "right": 3}) is None


def test_to_leaflet_bounds_none_when_zero_area():
    assert to_leaflet_bounds({"left": 0, "bottom": 0, "right": 0, "top": 0}) is None


def test_union_bbox_dicts_covers_all_inputs():
    a = {"left": 0, "bottom": 0, "right": 1, "top": 1}
    b = {"left": 2, "bottom": -3, "right": 4, "top": 2}
    assert union_bbox_dicts([a, b]) == [[-3, 0], [2, 4]]


def test_union_bbox_dicts_none_when_empty():
    assert union_bbox_dicts([]) is None
    assert union_bbox_dicts([{}, None]) is None
