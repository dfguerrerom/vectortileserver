import asyncio
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

    Caveat: the underlying tile server is a process-wide singleton, so
    ``host``/``port`` only take effect for the first server started in the
    process — workspaces created afterward share that same server regardless
    of what they were given. Likewise, ``stop()`` tears down that shared
    server for every ``TileWorkspace`` in the process, not just this one.
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
                self.port = client.server_port  # all clients share the one server
                self._clients[key] = client
            return client

    def open(self, source, *, style=None, layers_to_show=None, conversion_options=None):
        client = self._client_for(source, conversion_options)
        layer = client.create_leaflet_layer(style=style, layers_to_show=layers_to_show)
        layer.workspace = self
        return layer

    async def open_async(self, source, *, style=None, layers_to_show=None, conversion_options=None):
        """Convert (if needed) off-thread, then build the widget on the loop
        thread. Drops into Solara ``use_task(prefer_threaded=False)``."""
        # Conversion + server work is blocking and widget-free → offload it.
        client = await asyncio.to_thread(self._client_for, source, conversion_options)
        # Widget construction must stay on the calling (loop) thread.
        layer = client.create_leaflet_layer(style=style, layers_to_show=layers_to_show)
        layer.workspace = self
        return layer

    async def open_many(self, sources, *, style=None, layers_to_show=None, conversion_options=None):
        """Open many sources concurrently (parallel tippecanoe via the thread pool)."""
        return await asyncio.gather(
            *(
                self.open_async(
                    s,
                    style=style,
                    layers_to_show=layers_to_show,
                    conversion_options=conversion_options,
                )
                for s in sources
            )
        )

    def bounds(self):
        """Fit-ready union over every registered archive, or ``None``."""
        with self._lock:
            clients = list(self._clients.values())
        return union_bbox_dicts(c.metadata.get("bounds") for c in clients)

    def stop(self):
        """Best-effort shutdown of the shared server.

        This stops the process-global tile server, which is used by ALL
        ``TileWorkspace`` instances in the process — not just this one.
        """
        from vectortileserver.server import TileServer

        if TileServer._instance is not None:
            TileServer._instance.stop()


_DEFAULT_WORKSPACE: Optional[TileWorkspace] = None


def default_workspace() -> TileWorkspace:
    """Process-wide workspace backing the module-level ``open*`` helpers."""
    global _DEFAULT_WORKSPACE
    if _DEFAULT_WORKSPACE is None:
        _DEFAULT_WORKSPACE = TileWorkspace()
    return _DEFAULT_WORKSPACE


def open(source, *, style=None, layers_to_show=None, conversion_options=None):
    """Open a dataset on the default workspace (synchronous)."""
    return default_workspace().open(
        source, style=style, layers_to_show=layers_to_show, conversion_options=conversion_options
    )


async def open_async(source, *, style=None, layers_to_show=None, conversion_options=None):
    """Open a dataset on the default workspace, converting off-thread."""
    return await default_workspace().open_async(
        source, style=style, layers_to_show=layers_to_show, conversion_options=conversion_options
    )


async def open_many(sources, *, style=None, layers_to_show=None, conversion_options=None):
    """Open many datasets on the default workspace, in parallel."""
    return await default_workspace().open_many(
        sources, style=style, layers_to_show=layers_to_show, conversion_options=conversion_options
    )
