import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from vectortileserver.handler import union_bbox_dicts


def _source_key(source) -> str:
    from vectortileserver.client import TileClient

    if isinstance(source, TileClient):
        return str(Path(source.pmtiles_path).resolve())
    return str(Path(source).resolve())


class TileWorkspace:
    """Owns conversion scheduling, a source→client registry, and union bounds
    for many datasets sharing one tile server. Wraps :class:`TileClient`; the
    server itself is already multi-file.

    A source is converted and cached on first open; ``conversion_options``
    given when reopening an already-cached source are ignored — build a new
    ``TileWorkspace`` to reconvert with different options.
    """

    def __init__(
        self,
        *,
        host: str = "localhost",
        port: Optional[int] = None,
        allowed_directories: Optional[List[Union[str, Path]]] = None,
        client_prefix: Optional[str] = None,
        conversion_options: Optional[Dict[str, Any]] = None,
    ):
        self.host = host
        self.port = port
        self.allowed_directories = allowed_directories
        self.client_prefix = client_prefix
        self.default_conversion_options = conversion_options or {}
        self._clients: Dict[str, "object"] = {}
        self._lock = threading.Lock()
        self._keylocks = {}

    def _construction_lock(self, key):
        with self._lock:
            lock = self._keylocks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._keylocks[key] = lock
            return lock

    def _client_for(self, source, conversion_options):
        from vectortileserver.client import TileClient

        key = _source_key(source)
        with self._lock:
            client = self._clients.get(key)
        if client is not None:
            return client
        with self._construction_lock(key):
            # Re-check under the per-source lock: a thread we queued behind may
            # have finished building this client while we waited.
            with self._lock:
                client = self._clients.get(key)
            if client is not None:
                return client
            if isinstance(source, TileClient):
                client = source
            else:
                client = TileClient(
                    source,
                    host=self.host,
                    port=self.port,
                    allowed_directories=self.allowed_directories,
                    client_prefix=self.client_prefix,
                    conversion_options={
                        **self.default_conversion_options,
                        **(conversion_options or {}),
                    },
                )
            with self._lock:
                self.port = client.server_port
                self._clients[key] = client
            return client

    def open(self, source, *, style=None, layers_to_show=None, conversion_options=None):
        client = self._client_for(source, conversion_options)
        layer = client.create_leaflet_layer(style=style, layers_to_show=layers_to_show)
        layer.workspace = self
        return layer

    def bounds(self):
        """Fit-ready union over every registered archive, or ``None``."""
        return union_bbox_dicts(c.metadata.get("bounds") for c in self._clients.values())

    def stop(self):
        """Best-effort shutdown of the shared server."""
        from vectortileserver.server import TileServer

        if TileServer._instance is not None:
            TileServer._instance.stop()
