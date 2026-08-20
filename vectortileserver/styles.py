import colorsys
import random
from typing import Callable, List, Optional, Union


def generate_color_palette(palette_type="vibrant", num_colors=5):
    """
    Generate a color palette with different styles.

    Args:
        palette_type (str): Type of color palette
            Options: 'vibrant', 'pastel', 'earth', 'cool', 'warm'
        num_colors (int): Number of colors to generate

    Returns:
        list: List of hex color codes
    """
    palettes = {
        "vibrant": [
            "#FF6B6B",
            "#4ECDC4",
            "#45B7D1",
            "#FDCB6E",
            "#6C5CE7",  # Vibrant mix
            "#FF4500",
            "#1E90FF",
            "#32CD32",
            "#FF1493",
            "#FFD700",
        ],
        "pastel": [
            "#FFB3BA",
            "#BAFFC9",
            "#BAE1FF",
            "#FFFFBA",
            "#FFDFBA",
            "#E0BBE4",
            "#D4F0F0",
            "#DAEAF6",
            "#FFC6FF",
            "#F7EDE2",
        ],
        "earth": [
            "#8B4513",
            "#A0522D",
            "#D2691E",
            "#CD853F",
            "#DEB887",
            "#6B4423",
            "#5D4037",
            "#3E2723",
            "#795548",
            "#6D4C41",
        ],
        "cool": [
            "#0077BE",
            "#00A86B",
            "#4682B4",
            "#5F9EA0",
            "#48D1CC",
            "#20B2AA",
            "#008080",
            "#4169E1",
            "#1E90FF",
            "#6495ED",
        ],
        "warm": [
            "#FF4500",
            "#FF6347",
            "#FF7F50",
            "#FFD700",
            "#FFA500",
            "#FF8C00",
            "#FF4500",
            "#DC143C",
            "#B22222",
            "#FF1493",
        ],
    }

    colors = palettes.get(palette_type, palettes["cool"])

    # If not enough colors, generate additional colors
    while len(colors) < num_colors:
        # Generate a new random color with better color distribution
        h = random.random()
        s = 0.5 + random.random() * 0.5
        v = 0.5 + random.random() * 0.5

        r, g, b = [int(x * 255) for x in colorsys.hsv_to_rgb(h, s, v)]
        new_color = f"#{r:02x}{g:02x}{b:02x}"
        colors.append(new_color)

    return colors[:num_colors]


_SOURCE = "pmtiles_source"


def _palette(name: str = "earth") -> List[str]:
    return generate_color_palette(name, 10)


#: Painted on features whose ``field`` value was never assigned a color.
_UNMATCHED_COLOR = "#CCCCCC"


def _source_block(pmtiles_url: str) -> dict:
    return {_SOURCE: {"type": "vector", "url": f"pmtiles://{pmtiles_url}"}}


def _fill_layer(layer_id, minzoom, maxzoom, color):
    opacity = 0 if layer_id.lower() in ("mask", "earth") else 0.5
    return {
        "id": f"{layer_id}-fill",
        "type": "fill",
        "source": _SOURCE,
        "source-layer": layer_id,
        "minzoom": minzoom,
        "maxzoom": maxzoom,
        "paint": {"fill-color": color, "fill-opacity": opacity},
    }


def _outline_layer(layer_id, minzoom, maxzoom):
    return {
        "id": f"{layer_id}-outline",
        "type": "line",
        "source": _SOURCE,
        "source-layer": layer_id,
        "minzoom": minzoom,
        "maxzoom": maxzoom,
        "paint": {"line-color": "#000000", "line-width": 1},
    }


def _circle_layer(layer_id, minzoom, maxzoom, color):
    return {
        "id": f"{layer_id}-circle",
        "type": "circle",
        "source": _SOURCE,
        "source-layer": layer_id,
        "minzoom": minzoom,
        "maxzoom": maxzoom,
        "paint": {
            "circle-radius": 5,
            "circle-color": color,
            "circle-stroke-color": "#ffffff",
            "circle-stroke-width": 1,
            "circle-opacity": 0.85,
        },
    }


def _style_from_colors(metadata: dict, pmtiles_url: str, color_for) -> dict:
    """Emit fill + outline + circle for each vector layer. ``color_for(index)``
    supplies the fill/circle paint (a hex string or a MapLibre expression)."""
    layers = []
    for i, vector_layer in enumerate(metadata.get("vector_layers", [])):
        lid = vector_layer.get("id")
        minz = vector_layer.get("minzoom", 0)
        maxz = vector_layer.get("maxzoom", 22)
        color = color_for(i)
        layers.append(_fill_layer(lid, minz, maxz, color))
        layers.append(_outline_layer(lid, minz, maxz))
        layers.append(_circle_layer(lid, minz, maxz, color))
    return {"version": 8, "sources": _source_block(pmtiles_url), "layers": layers}


def default_style(metadata: dict, pmtiles_url: str, *, palette: str = "earth") -> dict:
    """Geometry-agnostic default: fill + outline + circle per vector layer, each
    symbolizer rendering only its matching geometry. Deterministic palette."""
    colors = _palette(palette)
    return _style_from_colors(metadata, pmtiles_url, lambda i: colors[i % len(colors)])


def single_symbol_style(*, color: str = "#3388ff") -> Callable[[dict, str], dict]:
    """Style builder: every vector layer painted a single ``color``."""
    return lambda metadata, pmtiles_url: _style_from_colors(metadata, pmtiles_url, lambda i: color)


def _scoped(layer: dict, suffix: str, selector: Optional[list]) -> dict:
    """Copy ``layer`` under a unique id, drawing only what ``selector`` picks."""
    scoped = {**layer, "id": f"{layer['id']}-{suffix}"}
    if selector is not None:
        scoped["filter"] = selector

    return scoped


def _categorized_layers(metadata: dict, pmtiles_url: str, buckets: list) -> dict:
    """Emit one fill + circle pair per bucket, plus the shared outline."""
    layers = []
    for vector_layer in metadata.get("vector_layers", []):
        lid = vector_layer.get("id")
        minz = vector_layer.get("minzoom", 0)
        maxz = vector_layer.get("maxzoom", 22)
        for suffix, color, selector in buckets:
            layers.append(_scoped(_fill_layer(lid, minz, maxz, color), suffix, selector))
            layers.append(_scoped(_circle_layer(lid, minz, maxz, color), suffix, selector))
        # One neutral outline for every feature, as in the other builders.
        layers.append(_outline_layer(lid, minz, maxz))
    return {"version": 8, "sources": _source_block(pmtiles_url), "layers": layers}


def categorized_style(
    field: str,
    values: list,
    *,
    palette: str = "earth",
    colors: Optional[List[str]] = None,
) -> Callable[[dict, str], dict]:
    """Style builder: color by ``field``, one color per value.

    Selects with filters rather than a ``["match", ["get", field], ...]`` paint
    expression. protomaps-leaflet -- what renders these styles under
    ipyleaflet's ``PMTilesLayer`` -- evaluates filters (``in``, ``!in``, ``==``,
    comparisons) but has only one paint function, zoom interpolation. A match
    expression is not evaluated there and silently paints every feature one
    flat color, which is the whole point of this builder lost with no error.

    One fill/circle pair is emitted per distinct color, so the layer count
    follows the palette rather than the length of ``values``.

    Args:
        field: feature property to switch on.
        values: values to assign colors to, in order.
        palette: named palette used when ``colors`` is not given.
        colors: explicit colors, cycled if shorter than ``values``. Pass this to
            reuse an assignment the caller already made elsewhere, so the two
            cannot drift.

    Returns:
        A builder taking ``(metadata, pmtiles_url)``.

    Raises:
        ValueError: if ``colors`` is given but empty.
    """
    swatches = _palette(palette) if colors is None else colors
    if not swatches:
        raise ValueError("colors must not be empty")

    # Group by color first: values sharing one swatch share one layer, and dict
    # order keeps the emitted style stable between runs.
    groups: dict = {}
    for j, value in enumerate(values):
        groups.setdefault(swatches[j % len(swatches)], []).append(value)

    if values:
        buckets = [
            (str(index), color, ["in", field, *assigned])
            for index, (color, assigned) in enumerate(groups.items())
        ]
        # Anything the caller did not enumerate, matching the old fallback.
        buckets.append(("other", _UNMATCHED_COLOR, ["!in", field, *values]))
    else:
        buckets = [("other", _UNMATCHED_COLOR, None)]

    return lambda metadata, pmtiles_url: _categorized_layers(metadata, pmtiles_url, buckets)


def resolve_style(
    style: Union[dict, Callable[[dict, str], dict], None],
    metadata: dict,
    pmtiles_url: str,
) -> dict:
    """A full MapLibre dict passes through; a builder is called with
    ``(metadata, pmtiles_url)``; ``None`` yields :func:`default_style`."""
    if style is None:
        return default_style(metadata, pmtiles_url)
    if callable(style):
        return style(metadata, pmtiles_url)
    return style
