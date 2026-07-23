from vectortileserver.logger import logger


def _vts_bounds(m, layers=None):
    from vectortileserver.pmtiles_layer import VectorTileLayer

    candidates = layers if layers is not None else getattr(m, "layers", [])
    return [
        layer.bounds for layer in candidates if isinstance(layer, VectorTileLayer) and layer.bounds
    ]


def union_bounds(m, layers=None):
    """Fit-ready ``[[S,W],[N,E]]`` covering every :class:`VectorTileLayer` on the
    map (or in ``layers``), or ``None`` when there are none with bounds."""
    boxes = _vts_bounds(m, layers)
    if not boxes:
        return None
    return [
        [min(b[0][0] for b in boxes), min(b[0][1] for b in boxes)],
        [max(b[1][0] for b in boxes), max(b[1][1] for b in boxes)],
    ]


def fit(m, layers=None):
    """Zoom ``m`` to fit its vector-tile layers. No-op (with a debug log) when
    none carry bounds."""
    bounds = union_bounds(m, layers)
    if bounds is None:
        logger.debug("fit: no bounded VectorTileLayer on the map; skipping")
        return
    m.fit_bounds(bounds)
