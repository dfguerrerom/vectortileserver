import asyncio
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from vectortileserver.archive import TileArchive
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
        host: str = "127.0.0.1",
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

    def _archive(self, client) -> TileArchive:
        # The browser, not this process, fetches the tiles: bridge the loopback
        # port before handing out a URL, or nothing loads under Voila / SEPAL.
        client.enable_jupyter_loopback()
        return TileArchive._from_client(client, workspace=self)

    def open(self, source, *, conversion_options=None) -> TileArchive:
        """Convert ``source`` if needed, serve it, and describe what is served.

        Build an ipyleaflet layer from the result with
        :meth:`TileArchive.create_leaflet_layer`.
        """
        return self._archive(self._client_for(source, conversion_options))

    async def open_async(self, source, *, conversion_options=None) -> TileArchive:
        """Like :meth:`open`, converting off-thread. Drops into Solara
        ``use_task(prefer_threaded=False)``."""
        # Conversion + server work is blocking and widget-free → offload it.
        client = await asyncio.to_thread(self._client_for, source, conversion_options)
        # The bridge emits a widget, so it is installed on the calling (loop) thread.
        return self._archive(client)

    async def open_many(self, sources, *, conversion_options=None) -> List[TileArchive]:
        """Open many sources concurrently (parallel tippecanoe via the thread pool)."""
        return await asyncio.gather(
            *(self.open_async(s, conversion_options=conversion_options) for s in sources)
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


def open(source, *, conversion_options=None) -> TileArchive:
    """Open a dataset on the default workspace (synchronous)."""
    return default_workspace().open(source, conversion_options=conversion_options)


async def open_async(source, *, conversion_options=None) -> TileArchive:
    """Open a dataset on the default workspace, converting off-thread."""
    return await default_workspace().open_async(source, conversion_options=conversion_options)


async def open_many(sources, *, conversion_options=None) -> List[TileArchive]:
    """Open many datasets on the default workspace, in parallel."""
    return await default_workspace().open_many(sources, conversion_options=conversion_options)
