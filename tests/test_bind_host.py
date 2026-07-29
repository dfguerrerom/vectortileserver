"""The tile server binds IPv4 loopback by default.

``"localhost"`` can resolve to IPv6 ``::1`` (via /etc/hosts), which some sandboxes
can't assign -> the server fails to bind and never starts. ``127.0.0.1`` is also
the exact literal jupyter_loopback's browser interceptor matches.
"""

from vectortileserver.server import ServerConfig
from vectortileserver.workspace import TileWorkspace


def test_server_config_default_host_is_ipv4():
    assert ServerConfig().host == "127.0.0.1"


def test_workspace_default_host_is_ipv4():
    assert TileWorkspace().host == "127.0.0.1"
