from pathlib import Path
from urllib.parse import unquote

from ipyleaflet import PMTilesLayer

from vectortileserver.feature_query import query_rendered_features_from_pmtiles
from vectortileserver.handler import to_leaflet_bounds
from vectortileserver.styles import resolve_style


class VectorTileLayer(PMTilesLayer):
    """An ipyleaflet ``PMTilesLayer`` that also knows its own extent and how to
    restyle itself. Build it through :meth:`_from_archive` (the client/workspace
    do this) so ``bounds``/``center``/``list_layers`` are populated."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Non-trait metadata; set after super().__init__ so traitlets is ready.
        self._vts_bounds = None
        self._vts_center = None
        self._vts_source = None
        self._vts_vector_layers = []
        self._vts_metadata = {}
        self.workspace = None

    @classmethod
    def _from_archive(
        cls,
        *,
        url,
        style,
        metadata,
        source=None,
        workspace=None,
        attribution="Vector Tile Server",
    ):
        layer = cls(url=url, style=style, attribution=attribution)
        layer._vts_metadata = metadata or {}
        layer._vts_vector_layers = layer._vts_metadata.get("vector_layers", [])
        layer._vts_bounds = to_leaflet_bounds(layer._vts_metadata.get("bounds"))
        center = layer._vts_metadata.get("center")
        layer._vts_center = tuple(center) if center else None
        layer._vts_source = Path(source) if source else None
        layer.workspace = workspace
        return layer

    @property
    def bounds(self):
        """``[[south, west], [north, east]]`` or ``None`` for an unbounded archive."""
        return self._vts_bounds

    @property
    def center(self):
        """``(lat, lon)`` or ``None``."""
        return self._vts_center

    @property
    def source(self):
        return self._vts_source

    @property
    def pmtiles_path(self):
        # ``filePath`` is percent-encoded in the URL so paths with spaces / ``#`` /
        # ``&`` survive the query string.
        return unquote(self.url.split("filePath=")[1])

    def list_layers(self):
        """Vector layer ids inside this archive."""
        return [vl.get("id") for vl in self._vts_vector_layers]

    def with_style(self, style):
        """Return a NEW layer over the same archive with a different style.
        Cheap — no reconversion; swap it in with ``m.remove(old); m.add(new)``.
        (Reassigning ``.style`` does not repaint: the ipyleaflet PMTiles frontend
        only observes ``change:url``.)"""
        return VectorTileLayer._from_archive(
            url=self.url,
            style=resolve_style(style, self._vts_metadata, self.url),
            metadata=self._vts_metadata,
            source=self._vts_source,
            workspace=self.workspace,
            attribution=self.attribution,
        )

    def get_data_from_coords(self, lat, lon, zoom):
        """Get features at a specific latitude, longitude, and zoom level."""
        data = query_rendered_features_from_pmtiles(self.pmtiles_path, self.style, lat, lon, zoom)
        for element in data:
            if "geometry" in element["feature"]:
                del element["feature"]["geometry"]
        return data


# Back-compat: existing imports of LeafletPMTilesLayer keep working.
LeafletPMTilesLayer = VectorTileLayer
