from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Union

from pmtiles.reader import MmapSource, Reader


def get_metadata(pmtiles_path: Union[str, Path]) -> Dict[str, Any]:
    """Get metadata from a PMTiles file."""

    with open(pmtiles_path, "rb") as f:
        reader = Reader(MmapSource(f))
        header = reader.header()
        metadata = reader.metadata()

    bounds = parse_bounds(header)

    return {
        **metadata,
        "bounds": bounds,
        "center": calculate_center(bounds),
    }


def parse_bounds(header, decimal_places: int = 7):
    left, bottom, right, top = (
        header["min_lon_e7"] / 1e7,
        header["min_lat_e7"] / 1e7,
        header["max_lon_e7"] / 1e7,
        header["max_lat_e7"] / 1e7,
    )

    return {
        "left": round(left, decimal_places),
        "bottom": round(bottom, decimal_places),
        "right": round(right, decimal_places),
        "top": round(top, decimal_places),
    }


def calculate_center(bounds):
    """Get center in the form of (y <lat>, x <lon>)"""

    extent = (bounds["bottom"], bounds["top"], bounds["left"], bounds["right"])

    return (
        (extent[1] - extent[0]) / 2 + extent[0],
        (extent[3] - extent[2]) / 2 + extent[2],
    )


_BBOX_KEYS = ("left", "bottom", "right", "top")


def _valid_bbox(bounds: Optional[dict]) -> bool:
    return bool(bounds) and all(bounds.get(k) is not None for k in _BBOX_KEYS)


def to_leaflet_bounds(bounds: Optional[dict]) -> Optional[List[List[float]]]:
    """Convert a ``{'left','bottom','right','top'}`` bbox to ipyleaflet's
    ``[[south, west], [north, east]]``. Returns ``None`` for a missing, partial,
    or zero-area box so callers can skip fitting instead of zooming to a point."""
    if not _valid_bbox(bounds):
        return None
    left, bottom, right, top = (bounds[k] for k in _BBOX_KEYS)
    if left == right or bottom == top:
        return None
    return [[bottom, left], [top, right]]


def union_bbox_dicts(dicts: Iterable[Optional[dict]]) -> Optional[List[List[float]]]:
    """Fit-ready union of several bbox dicts; ``None`` when none are valid."""
    valid = [d for d in dicts if _valid_bbox(d)]
    if not valid:
        return None
    return to_leaflet_bounds(
        {
            "left": min(d["left"] for d in valid),
            "bottom": min(d["bottom"] for d in valid),
            "right": max(d["right"] for d in valid),
            "top": max(d["top"] for d in valid),
        }
    )
