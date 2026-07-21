"""
Client-side connection configuration.

The kernel reaches its own tile server over loopback, but the *browser* often
cannot: under JupyterHub, Voila, or SEPAL the notebook page is served from a
different origin than ``http://localhost:<port>``. ``jupyter_loopback`` solves
this by mounting an HTTP proxy on the jupyter-server at
``<base_url>/vectortileserver-proxy/<port>/…``; this module works out the prefix
to put in front of browser-facing URLs so they land there.
"""

import os
from typing import Optional

from vectortileserver.logger import logger

#: Namespace passed to :func:`jupyter_loopback.setup_proxy_handler` in
#: :mod:`vectortileserver._jupyter`. Autodetection must use the same string.
LOOPBACK_NAMESPACE = "vectortileserver"

_PREFIX_ENV_VAR = "VECTORTILESERVER_CLIENT_PREFIX"


def get_default_client_prefix(prefix: Optional[str] = None) -> Optional[str]:
    """
    Resolve the URL prefix the browser should use to reach the tile server.

    Resolution order:

    1. The explicit ``prefix`` argument.
    2. The ``VECTORTILESERVER_CLIENT_PREFIX`` environment variable. Setting it
       to an empty string forces the plain loopback URL, which is the escape
       hatch when autodetection guesses wrong.
    3. :func:`jupyter_loopback.autodetect_prefix`, which returns a prefix only
       inside a Jupyter kernel.

    Args:
        prefix: Explicit prefix, possibly containing a ``{port}`` placeholder.

    Returns:
        The prefix template, or ``None`` to use the loopback URL directly.
    """
    if prefix is not None:
        return prefix or None

    env_prefix = os.environ.get(_PREFIX_ENV_VAR)
    if env_prefix is not None:
        return env_prefix or None

    try:
        from jupyter_loopback import autodetect_prefix
    except ImportError:
        return None

    auto = autodetect_prefix(LOOPBACK_NAMESPACE)
    if auto is not None:
        logger.debug(f"Autodetected Jupyter proxy prefix: {auto}")

    return auto
