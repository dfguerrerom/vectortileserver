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


def test_categorized_style_builds_a_match_expression():
    build = categorized_style("map_code", [0, 1, 2])
    style = build(META, URL)
    circle = next(layer for layer in style["layers"] if layer["type"] == "circle")
    expr = circle["paint"]["circle-color"]
    assert expr[0] == "match" and expr[1] == ["get", "map_code"]


def test_resolve_style_passes_dicts_through_and_calls_builders():
    assert resolve_style({"version": 8, "layers": []}, META, URL) == {"version": 8, "layers": []}
    assert resolve_style(None, META, URL) == default_style(META, URL)
    assert resolve_style(single_symbol_style(color="#000000"), META, URL)["layers"]


def test_categorized_style_uses_explicit_colors():
    build = categorized_style("map_code", [0, 1], colors=["#111111", "#222222"])
    style = build(META, URL)
    circle = next(layer for layer in style["layers"] if layer["type"] == "circle")

    assert circle["paint"]["circle-color"] == [
        "match",
        ["get", "map_code"],
        0,
        "#111111",
        1,
        "#222222",
        "#CCCCCC",
    ]


def test_categorized_style_cycles_explicit_colors():
    build = categorized_style("map_code", [0, 1, 2], colors=["#111111", "#222222"])
    style = build(META, URL)
    circle = next(layer for layer in style["layers"] if layer["type"] == "circle")

    assert circle["paint"]["circle-color"][7] == "#111111"


def test_categorized_style_rejects_an_empty_color_list():
    with pytest.raises(ValueError):
        categorized_style("map_code", [0], colors=[])
