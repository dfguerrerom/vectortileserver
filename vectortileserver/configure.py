"""
Client-side connection configuration.

The kernel reaches its own tile server over loopback; the *browser* reaches it
through the ``jupyter_loopback`` comm bridge (see
:mod:`vectortileserver._jupyter_loopback_bridge`), which works in every frontend.

A URL prefix is only needed when the tile server is fronted by a reverse proxy
the caller sets up themselves, so it is a manual override rather than something
autodetected — an autodetected proxy prefix cannot be relied on (e.g. Voila,
which is a separate server, answers the detection probe with a 405 and then 403s
the tile request).
"""

import os
from typing import Optional

_PREFIX_ENV_VAR = "VECTORTILESERVER_CLIENT_PREFIX"


def get_default_client_prefix(prefix: Optional[str] = None) -> Optional[str]:
    """
    Resolve an optional URL prefix for browser-facing tile URLs.

    Returns ``None`` by default: the tile URL is then the loopback URL and the
    comm bridge tunnels it over the kernel's comm channel. Supply a prefix only
    to route through a reverse proxy you control.

    Resolution order:

    1. The explicit ``prefix`` argument (an empty string forces loopback).
    2. ``VECTORTILESERVER_CLIENT_PREFIX`` (an empty string forces loopback).
    3. Otherwise ``None`` — loopback URL + comm bridge.

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

    return None
