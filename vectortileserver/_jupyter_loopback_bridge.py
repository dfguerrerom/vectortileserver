"""
Route tile URLs through the ``jupyter_loopback`` comm bridge.

PMTiles are read by the browser with HTTP Range requests against the tile
server running inside the kernel. In JupyterLab and Notebook 7 the notebook
page shares an origin with the jupyter-server, so either the loopback URL or
the proxy prefix from :mod:`vectortileserver.configure` gets there. Voila,
VS Code Jupyter, and Colab render outputs in a sandboxed webview whose
origin is *not* the jupyter-server: ``http://localhost:<port>`` is unreachable
and tiles silently fail.

:func:`enable_for_port` hands the port to ``jupyter_loopback``, which opens a
second channel — the kernel's own comm websocket — and installs a DOM shim that
rewrites matching ``fetch`` / ``XMLHttpRequest`` / ``<img src>`` calls to travel
over it. The shim forwards request headers untouched and rebuilds the upstream
status, so ``Range`` and ``206 Partial Content`` survive the trip, which is what
makes PMTiles work at all.

When ``path_prefix`` is supplied the browser probes it once: if the jupyter-server
really does host the proxy, the faster direct HTTP path keeps serving tiles and
the bridge stays idle. Opt out entirely with
``VECTORTILESERVER_DISABLE_JUPYTER_LOOPBACK=1``.
"""

import os
from typing import Optional, Set, Tuple

from vectortileserver.logger import logger

_DISABLE_ENV_VAR = "VECTORTILESERVER_DISABLE_JUPYTER_LOOPBACK"

# Ports already handed to ``jupyter_loopback.intercept_localhost`` in this
# kernel. Deduplicating here keeps layer creation idempotent from the user's
# point of view: building ten layers must not emit ten <script> tags. Keyed by
# (port, prefix) so changing the prefix for a known port still propagates.
_INTERCEPTED: Set[Tuple[int, Optional[str]]] = set()

# One-shot flags so a broken install produces a single actionable log line
# rather than one per layer. Kept separate so an early ImportError does not
# mask a different failure later on.
_warned_unavailable = False
_warned_failure = False


def _is_disabled() -> bool:
    """Return ``True`` when the opt-out environment variable is set."""
    value = os.environ.get(_DISABLE_ENV_VAR, "")
    return value.lower() not in ("", "0", "false", "no", "off")


def enable_for_port(port: Optional[int], *, path_prefix: Optional[str] = None) -> None:
    """
    Install the jupyter-loopback interceptor for a single loopback port.

    Safe to call repeatedly: only the first call for a given
    ``(port, path_prefix)`` pair emits the bridge widget and the shim. No-ops
    when ``port`` is ``None`` or the opt-out variable is set.

    Args:
        port: Loopback port of the tile server, i.e. ``TileClient.server_port``.
        path_prefix: Absolute URL path (with ``{port}`` already substituted)
            that also routes to this port through the jupyter-server proxy.
            Supplying it lets the browser prefer direct HTTP where that works.
    """
    global _warned_unavailable, _warned_failure

    if port is None or _is_disabled():
        return

    port_int = int(port)
    prefix_clean = (path_prefix or "").rstrip("/") or None
    key = (port_int, prefix_clean)
    if key in _INTERCEPTED:
        return

    try:
        import jupyter_loopback

        if not jupyter_loopback.is_comm_bridge_enabled():
            jupyter_loopback.enable_comm_bridge()
        jupyter_loopback.intercept_localhost(port_int, path_prefix=prefix_clean)
    except ImportError as e:
        # Usually the `[comm]` extra (anywidget) is missing. Say so once,
        # loudly: without it the bridge is dormant and tiles fail in exactly
        # the frontends this exists for.
        if not _warned_unavailable:
            logger.warning(
                f"Cannot enable the jupyter-loopback comm bridge: {e}. Tiles may not load "
                "in Voila / VS Code / Colab. Install it with "
                "`pip install jupyter-loopback[comm]`."
            )
            _warned_unavailable = True
        return
    except Exception as e:
        # Called from layer construction, which must never blow up because the
        # bridge misbehaved. Degrade to "tiles fail" instead of "layer raises" —
        # but say so once, since the symptom (no tiles) is identical to the
        # ImportError case and just as invisible.
        if not _warned_failure:
            logger.warning(
                f"Could not set up the jupyter-loopback bridge: {e}. Tiles may not load "
                "in Voila / VS Code / Colab."
            )
            _warned_failure = True
        return

    _INTERCEPTED.add(key)


def enable_jupyter_loopback(
    port: Optional[int] = None,
    *,
    path_prefix: Optional[str] = None,
) -> None:
    """
    Ensure the comm bridge is active for a tile server port.

    :meth:`TileClient.create_leaflet_layer` already does this for its own port,
    so most callers never need it. Reach for it when a port did not flow through
    that path — for instance a :class:`~vectortileserver.server.TileServer`
    feeding custom HTML output. Repeated calls for the same port are no-ops.

    Args:
        port: Loopback port to intercept.
        path_prefix: Proxy path prefix that also routes to this port.
    """
    enable_for_port(port, path_prefix=path_prefix)
