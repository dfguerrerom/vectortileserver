import pytest

from vectortileserver.styles import (
    categorized_style,
    default_style,
    resolve_style,
    single_symbol_style,
)

META = {"vector_layers": [{"id": "points", "minzoom": 0, "maxzoom": 14}]}
URL = "http://x/pmtiles?filePath=/a.pmtiles"


def _types(style):
    return sorted({layer["type"] for layer in style["layers"]})


def test_default_style_emits_fill_line_and_circle_per_layer():
    style = default_style(META, URL)
    assert style["version"] == 8
    assert style["sources"]["pmtiles_source"]["url"] == f"pmtiles://{URL}"
    assert _types(style) == ["circle", "fill", "line"]
    assert all(layer["source-layer"] == "points" for layer in style["layers"])


def test_default_style_is_deterministic():
    assert default_style(META, URL) == default_style(META, URL)


def test_single_symbol_style_is_a_builder_using_one_color():
    build = single_symbol_style(color="#123456")
    style = build(META, URL)
    fills = [layer for layer in style["layers"] if layer["type"] == "fill"]
    assert fills and fills[0]["paint"]["fill-color"] == "#123456"


def _color_by_value(style, field):
    """Map each selected value to the color its layers paint it."""
    found = {}
    for layer in style["layers"]:
        if layer["type"] != "fill":
            continue
        selector = layer.get("filter")
        if selector is None or selector[0] != "in":
            continue
        assert selector[1] == field
        for value in selector[2:]:
            found[value] = layer["paint"]["fill-color"]

    return found


def _unmatched(style):
    return next(
        layer
        for layer in style["layers"]
        if layer["type"] == "fill" and layer["id"].endswith("-other")
    )


def test_categorized_style_selects_with_filters_not_a_paint_expression():
    """protomaps-leaflet evaluates filters; a match paint renders flat."""
    style = categorized_style("map_code", [0, 1, 2])(META, URL)

    for layer in style["layers"]:
        for value in layer["paint"].values():
            assert not isinstance(value, list), f"expression in paint: {value}"
    assert set(_color_by_value(style, "map_code")) == {0, 1, 2}


def test_categorized_style_uses_explicit_colors():
    style = categorized_style("map_code", [0, 1], colors=["#111111", "#222222"])(META, URL)

    assert _color_by_value(style, "map_code") == {0: "#111111", 1: "#222222"}


def test_categorized_style_cycles_explicit_colors():
    style = categorized_style("map_code", [0, 1, 2], colors=["#111111", "#222222"])(META, URL)

    assert _color_by_value(style, "map_code") == {
        0: "#111111",
        1: "#222222",
        2: "#111111",
    }


def test_categorized_style_groups_values_sharing_a_color():
    """Layer count follows the palette, not the number of values."""
    style = categorized_style("map_code", list(range(20)), colors=["#111111", "#222222"])(
        META, URL
    )
    fills = [layer for layer in style["layers"] if layer["type"] == "fill"]

    # two colors plus the unmatched bucket
    assert len(fills) == 3


def test_categorized_style_paints_unenumerated_values_the_fallback():
    style = categorized_style("map_code", [0, 1])(META, URL)
    other = _unmatched(style)

    assert other["filter"] == ["!in", "map_code", 0, 1]
    assert other["paint"]["fill-color"] == "#CCCCCC"


def test_categorized_style_with_no_values_paints_everything_the_fallback():
    style = categorized_style("map_code", [])(META, URL)
    other = _unmatched(style)

    assert "filter" not in other
    assert other["paint"]["fill-color"] == "#CCCCCC"


def test_categorized_style_keeps_one_outline_per_vector_layer():
    style = categorized_style("map_code", [0, 1, 2])(META, URL)
    lines = [layer for layer in style["layers"] if layer["type"] == "line"]

    assert len(lines) == 1
    assert "filter" not in lines[0]


def test_categorized_style_emits_unique_layer_ids():
    style = categorized_style("map_code", [0, 1, 2])(META, URL)
    ids = [layer["id"] for layer in style["layers"]]

    assert len(ids) == len(set(ids))


def test_categorized_style_is_deterministic():
    build = categorized_style("map_code", [0, 1, 2])
    assert build(META, URL) == build(META, URL)


def test_categorized_style_rejects_an_empty_color_list():
    with pytest.raises(ValueError):
        categorized_style("map_code", [0], colors=[])


def test_resolve_style_passes_dicts_through_and_calls_builders():
    assert resolve_style({"version": 8, "layers": []}, META, URL) == {"version": 8, "layers": []}
    assert resolve_style(None, META, URL) == default_style(META, URL)
    assert resolve_style(single_symbol_style(color="#000000"), META, URL)["layers"]


