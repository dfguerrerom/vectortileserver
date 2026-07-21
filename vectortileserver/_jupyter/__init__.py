"""
Jupyter Server extension registering the vectortileserver loopback proxy.

The proxy handler, auth handling, and URL autodetection all live in
``jupyter_loopback``. This module only wires them up for our namespace, so that
``<base_url>/vectortileserver-proxy/<port>/…`` forwards to the tile server
running inside the kernel. :mod:`vectortileserver.configure` builds URLs against
the same namespace on the client side.
"""

from typing import Any, Dict, List

from jupyter_loopback import setup_proxy_handler

from vectortileserver.configure import LOOPBACK_NAMESPACE

__all__ = ["_jupyter_server_extension_points", "_load_jupyter_server_extension"]


def _jupyter_server_extension_points() -> List[Dict[str, str]]:
    """Declare this package as a Jupyter Server extension."""
    return [{"module": "vectortileserver._jupyter"}]


def _load_jupyter_server_extension(server_app: Any) -> None:
    """Register the loopback proxy for the ``vectortileserver`` namespace."""
    setup_proxy_handler(server_app.web_app, namespace=LOOPBACK_NAMESPACE)
    server_app.log.info(
        "vectortileserver: proxy registered at %s%s-proxy/<port>/...",
        server_app.web_app.settings.get("base_url", "/"),
        LOOPBACK_NAMESPACE,
    )
