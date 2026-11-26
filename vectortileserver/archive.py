from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple, Union

from vectortileserver.handler import to_leaflet_bounds

if TYPE_CHECKING:
    from vectortileserver.client import TileClient
    from vectortileserver.pmtiles_layer import VectorTileLayer
    from vectortileserver.workspace import TileWorkspace


# eq=False: two opens of one source are the same archive only if they are the
# same object, and identity hashing tolerates the list-valued ``bounds``.
@dataclass(frozen=True, eq=False)
class TileArchive:
    """A served PMTiles archive, described without any map library.

    This is what :meth:`TileWorkspace.open` returns. Hand ``url`` to whatever reads
    PMTiles in the browser, such as MapLibre's ``pmtiles://`` protocol. The tile
    server's port is already bridged to the browser when you get it.
    :meth:`create_leaflet_layer` builds an ipyleaflet layer over the same archive,
    and needs the ``leaflet`` extra.

    Attributes:
        url: Browser-facing URL of the archive.
        layers: Vector layer ids inside the archive.
        bounds: ``[[south, west], [north, east]]``, or ``None`` for an unbounded or
            zero-area archive.
        center: ``(lat, lon)``, or ``None``.
        source: The dataset that was opened (the ``.pmtiles`` file itself when no
            conversion was needed).
        pmtiles_path: The archive on disk.
        client: The :class:`TileClient` serving it.
        workspace: The workspace that opened it, if any.
    """

    url: str
    layers: Tuple[str, ...]
    bounds: Optional[List[List[float]]]
    center: Optional[Tuple[float, float]]
    source: Path
    pmtiles_path: Path
    client: "TileClient" = field(repr=False)
    workspace: Optional["TileWorkspace"] = field(default=None, repr=False)

    @classmethod
    def _from_client(
        cls, client: "TileClient", workspace: Optional["TileWorkspace"] = None
    ) -> "TileArchive":
        metadata = client.metadata or {}
        center = metadata.get("center")
        return cls(
            url=client.pmtiles_url,
            layers=tuple(client.list_layers()),
            bounds=to_leaflet_bounds(metadata.get("bounds")),
            center=tuple(center) if center else None,
            source=client.data_source,
            pmtiles_path=Path(client.pmtiles_path),
            client=client,
            workspace=workspace,
        )

    @property
    def metadata(self) -> Dict[str, Any]:
        """The archive's PMTiles metadata (``vector_layers``, ``bounds``, ...)."""
        return self.client.metadata

    def list_layers(self) -> List[str]:
        """Vector layer ids inside the archive, as a list."""
        return list(self.layers)

    def create_leaflet_layer(
        self,
        style: Union[Dict[str, Any], Callable[[dict, str], dict], None] = None,
        layers_to_show: Optional[List[str]] = None,
    ) -> "VectorTileLayer":
        """Build an ipyleaflet layer over this archive. Needs the ``leaflet`` extra.

        Cheap: no reconversion. Call it on the thread that owns the widgets.

        Args:
            style: ``None`` for the default style, a full MapLibre style dict, or a
                builder ``(metadata, pmtiles_url) -> dict`` such as
                :func:`~vectortileserver.styles.categorized_style`.
            layers_to_show: Restrict the style to these layer ids.
        """
        layer = self.client.create_leaflet_layer(style=style, layers_to_show=layers_to_show)
        layer.workspace = self.workspace
        return layer
