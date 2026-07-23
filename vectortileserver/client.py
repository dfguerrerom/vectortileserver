import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import quote

import httpx

from vectortileserver._jupyter_loopback_bridge import enable_for_port
from vectortileserver.configure import get_default_client_prefix
from vectortileserver.converter import TileConverter
from vectortileserver.handler import get_metadata
from vectortileserver.logger import logger
from vectortileserver.server import TileServer
from vectortileserver.utils import is_port_in_use


def _conversion_record_path(pmtiles_path: Path) -> Path:
    """Sidecar file recording how an archive was built."""
    return pmtiles_path.with_name(pmtiles_path.name + ".json")


def _normalize_options(options: Dict[str, Any]) -> Dict[str, Any]:
    """Round-trip options through JSON so recorded and requested values compare equal."""
    return json.loads(json.dumps(options or {}, sort_keys=True, default=str))


def _read_conversion_options(pmtiles_path: Path) -> Optional[Dict[str, Any]]:
    """
    Options an archive was built with, or ``None`` when that is unknown.

    ``None`` means there is no readable record: either a pre-sidecar archive —
    possibly built by an older version whose defaults dropped points — or a
    corrupt one. The caller treats that as "cannot vouch for this archive" and
    reconverts, rather than assuming it matches the current settings.
    """
    try:
        record = json.loads(_conversion_record_path(pmtiles_path).read_text())
    except (OSError, ValueError):
        return None

    options = record.get("options")

    return options if isinstance(options, dict) else None


# Files that make up a shapefile dataset. A shapefile is not one file: editing
# attributes (.dbf), the projection (.prj), or the encoding (.cpg) changes the
# resulting tiles without touching the .shp, so all of them count toward cache
# freshness. Index files (.shx/.qix/...) do not change tile content, but a
# stale index is cheap to reconvert past and keeps the list simple.
_SHAPEFILE_SUFFIXES = frozenset(
    {".shp", ".shx", ".dbf", ".prj", ".cpg", ".sbn", ".sbx", ".qix", ".fbn", ".fbx"}
)


def _source_mtime(data_source: Path) -> float:
    """
    Newest mtime across the source dataset.

    For a shapefile this spans its sibling files so an attribute-only edit still
    invalidates a cached conversion. Single-file sources (GeoJSON, GPKG) just use
    their own mtime. Same-stem files that are not shapefile companions (a sibling
    ``.geojson``, the ``.pmtiles`` output, its ``.json`` sidecar) are ignored.
    """
    mtimes = [data_source.stat().st_mtime]

    if data_source.suffix.lower() == ".shp":
        for sibling in data_source.parent.glob(f"{data_source.stem}.*"):
            if sibling.suffix.lower() in _SHAPEFILE_SUFFIXES:
                try:
                    mtimes.append(sibling.stat().st_mtime)
                except OSError:
                    continue

    return max(mtimes)


def _write_conversion_options(pmtiles_path: Path, options: Dict[str, Any]) -> None:
    """Record the options used, so a later run can tell whether they changed."""
    try:
        _conversion_record_path(pmtiles_path).write_text(
            json.dumps({"options": _normalize_options(options)}, sort_keys=True, indent=2)
        )
    except OSError as e:
        # Losing the record only costs a redundant reconversion next time.
        logger.debug(f"Could not record conversion options: {e}")


class TileClient:
    """
    A client for accessing PMTiles from a local server.

    This class triggers the lazy initialization of the server if needed.
    """

    def __init__(
        self,
        data_source: Union[str, Path] | None = None,
        host: str = "localhost",
        port: Optional[int] = None,
        converter: Optional[TileConverter] = None,
        conversion_options: Dict[str, Any] | None = None,
        allowed_directories: List[Union[str, Path]] | None = None,
        http_client: Optional[httpx.AsyncClient] = None,
        client_prefix: Optional[str] = None,
    ):
        """
        Initialize the tile client.

        Args:
            data_source: Path to the vector data source (GeoJSON, Shapefile, PMTiles, etc.)
            host: Host where the server is running.
            port: Port where the server is running.
            converter: Custom TileConverter instance to use.
            conversion_options: Options to pass to the tile converter. These override
                :data:`~vectortileserver.converter.DEFAULT_CONVERSION_OPTIONS`, which
                keep every feature at every zoom level.
            allowed_directories: List of directories that can be accessed by the server.
            http_client: Custom HTTP client for testing.
            client_prefix: Optional URL prefix for a reverse proxy the caller fronts
                the server with. Left unset the tile URL is the loopback URL, tunneled
                to the browser by the comm bridge; pass an empty string to force that
                explicitly.
        """
        logger.debug(f"Initializing tile client with data source: {data_source}")

        if data_source is None:
            raise ValueError(
                "A data_source is required: pass a path to a PMTiles file or to a "
                "vector file (GeoJSON, Shapefile, GPKG, ...) to convert."
            )

        self.data_source = Path(data_source)
        self.host = host
        self.port = port
        self.converter = converter
        self.conversion_options = conversion_options or {}
        self.pmtiles_path = None
        self.allowed_directories = allowed_directories
        self._http_client = http_client
        self._client_prefix = get_default_client_prefix(client_prefix)

        self.pmtiles_directory = self.data_source.parent
        self.metadata = None

        self._process_data_source()

        if self.pmtiles_path is None:
            raise ValueError(
                "PMTiles file is not available. Ensure that a valid data_source is "
                "provided or that the pmtiles_directory contains a PMTiles file."
            )

        # Ensure the server is running
        self._ensure_server_running()

    @property
    def server_port(self) -> Optional[int]:
        """Loopback port the tile server is listening on."""
        return self.port

    @property
    def server_url(self) -> str:
        """Base URL of the tile server as reachable from this process."""
        return f"http://{self.host}:{self.port}"

    @property
    def client_prefix(self) -> Optional[str]:
        """URL prefix used by the browser for proxied access, or ``None``."""
        if self._client_prefix:
            return self._client_prefix.replace("{port}", str(self.server_port))
        return None

    @client_prefix.setter
    def client_prefix(self, value: Optional[str]) -> None:
        self._client_prefix = value

    @property
    def client_base_url(self) -> str:
        """
        Base URL the browser should use to reach the tile server.

        The loopback URL by default — the comm bridge tunnels it, which works in
        every frontend. When a reverse-proxy ``client_prefix`` is set, that path
        (or full URL) is used instead.
        """
        prefix = self.client_prefix
        if not prefix:
            return self.server_url
        if "://" in prefix:  # a full URL, not a path — leave it alone
            return prefix.rstrip("/")
        return f"/{prefix.strip('/')}"

    @property
    def pmtiles_url(self) -> str:
        """Get the URL for the PMTiles file with its filePath."""
        # `filePath` stays last on purpose: protomaps-leaflet decides whether to
        # read the source as a PMTiles archive by testing `url.endsWith(".pmtiles")`.
        # Percent-encoding keeps `.pmtiles` intact (`.` is never escaped) while
        # making paths containing `#`, `&`, or spaces survive the query string.
        file_path = quote(str(self.pmtiles_path), safe="/")

        return f"{self.client_base_url}/pmtiles?filePath={file_path}"

    @property
    def bounds(self) -> List:
        """Get the bounds of the PMTiles file."""
        return self.metadata.get("bounds", [])

    @property
    def center(self) -> Tuple:
        """Get the center of the PMTiles file."""
        return self.metadata.get("center", [])

    def get_metadata(self) -> Dict[str, Any]:
        """Get metadata for the PMTiles file."""
        return get_metadata(self.pmtiles_path)

    def list_layers(self):
        """Return a list of available vector layer IDs from the metadata."""
        return [layer.get("id") for layer in self.metadata.get("vector_layers", [])]

    def enable_jupyter_loopback(self) -> None:
        """
        Make this client's port reachable from sandboxed notebook frontends.

        :meth:`create_leaflet_layer` calls this already; use it directly only when
        building the tile URL into custom output.
        """
        enable_for_port(self.server_port, path_prefix=self.client_prefix)

    def _process_data_source(self) -> None:
        """Process the data source file."""

        if self.data_source.suffix.lower() == ".pmtiles":
            self._handle_pmtiles()

        else:
            cached = self.data_source.with_suffix(".pmtiles")
            if self._can_reuse(cached):
                logger.debug(f"Reusing up-to-date PMTiles file: {cached}")
                self.pmtiles_path = cached
            else:
                self._convert_vector_data()

        self.metadata = self.get_metadata()

    def _can_reuse(self, cached: Path) -> bool:
        """
        Decide whether a previous conversion still stands in for this one.

        Scoped to the file we would have written: checking the directory for any
        .pmtiles instead would let an unrelated leftover block conversion
        entirely. The source dataset's mtime and the recorded options are both
        part of the archive's identity — a newer source, different tippecanoe
        settings, or an archive we can't vouch for all force a rebuild rather
        than silently serving the previous build.
        """
        if not cached.exists():
            return False

        if cached.stat().st_mtime < _source_mtime(self.data_source):
            return False

        recorded = _read_conversion_options(cached)
        if recorded is None:
            logger.debug(f"No conversion record for {cached}; reconverting under current settings")
            return False
        if recorded != _normalize_options(self.conversion_options):
            logger.debug(f"Conversion options changed since {cached} was built; reconverting")
            return False

        return True

    def _handle_pmtiles(self) -> None:
        """Handle a PMTiles file directly without conversion.

        If the metadata file is not present in the same folder as the PMTiles file,
        create it.
        """
        logger.debug(f"Using PMTiles file directly: {self.data_source}")

        if not self.data_source.exists():
            raise FileNotFoundError(f"PMTiles file not found: {self.data_source}")

        # The archive lives in its own directory already; serve it in place.
        self.pmtiles_path = self.data_source

    def _convert_vector_data(self) -> None:
        """
        Process vector data formats and convert to PMTiles if needed.
        """
        logger.debug(f"Processing vector data: {self.data_source} -> {self.pmtiles_directory}")

        # Use provided converter or create a new one
        converter = self.converter
        if not converter:
            converter = TileConverter(self.data_source, self.pmtiles_directory)

        # Convert the data
        pmtiles_path = converter.convert(**self.conversion_options)

        if not pmtiles_path or not Path(pmtiles_path).is_file():
            raise RuntimeError(f"No PMTiles file was generated in {self.pmtiles_directory}")

        _write_conversion_options(Path(pmtiles_path), self.conversion_options)

        logger.debug(f"Converted data to PMTiles: {pmtiles_path}")
        self.pmtiles_path = Path(pmtiles_path)

    def _ensure_server_running(self) -> None:
        """
        Ensure the tile server is running.
        """
        if self.port is not None and is_port_in_use(self.port):
            logger.debug(f"Using existing server at port {self.port}")
            return

        server = TileServer.get_instance(
            host=self.host,
            port=self.port,
            allowed_directories=[self.pmtiles_directory] + (self.allowed_directories or []),
        )
        self.port = server.config.port

    def create_leaflet_layer(
        self,
        style: Optional[Dict[str, Any]] = None,
        layers_to_show: Optional[List[str]] = None,
    ) -> Any:
        """Create a PMTiles layer for ipyleaflet.

        Args:
            style: Optional custom style for the layer. May be ``None`` (auto default style),
                a full MapLibre style dict (passed through), or a builder callable
                ``(metadata, pmtiles_url) -> dict``.
            layers_to_show: Restrict the rendered style to these layer IDs.
        """
        try:
            from vectortileserver.pmtiles_layer import VectorTileLayer
        except ImportError as e:
            raise ImportError(
                "ipyleaflet is required to create a leaflet layer. "
                "Install it with 'pip install ipyleaflet'."
            ) from e

        from vectortileserver.styles import resolve_style

        # The browser, not this process, fetches the tiles. Bridge the loopback
        # port before handing out a URL, or nothing loads under Voila/SEPAL.
        self.enable_jupyter_loopback()

        style_json = resolve_style(style, self.metadata, self.pmtiles_url)

        if layers_to_show:
            if not all(layer in self.list_layers() for layer in layers_to_show):
                raise ValueError(
                    f"Invalid layer IDs provided. Available layers: {self.list_layers()}"
                )
            style_json = {
                **style_json,
                "layers": [
                    layer
                    for layer in style_json.get("layers", [])
                    if layer.get("source-layer") in layers_to_show
                ],
            }

        return VectorTileLayer._from_archive(
            url=self.pmtiles_url,
            style=style_json,
            metadata=self.metadata,
            source=self.data_source,
        )
