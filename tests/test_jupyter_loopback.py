"""
Reaching the tile server from the browser (issue #3).

PMTiles are read with HTTP Range requests. The browser reaches the kernel's
loopback tile server through the jupyter_loopback comm bridge — which works in
every frontend (JupyterLab, Voila, VS Code, Colab). What matters is that
`Range` and `206` survive that trip. A URL prefix is a manual reverse-proxy
override, nothing more; there is deliberately no autodetected proxy path.
"""

import sys

import pytest

from vectortileserver import _jupyter_loopback_bridge as bridge
from vectortileserver.client import TileClient
from vectortileserver.configure import get_default_client_prefix


@pytest.fixture
def client(pmtiles_file):
    return TileClient(data_source=pmtiles_file, allowed_directories=[pmtiles_file.parent])


# --------------------------------------------------------------------------- #
# Prefix resolution                                                             #
# --------------------------------------------------------------------------- #


def test_no_prefix_by_default():
    assert get_default_client_prefix() is None


def test_no_prefix_is_autodetected_inside_a_kernel(monkeypatch):
    """
    Regression: a kernel used to autodetect a jupyter-server proxy prefix, which
    breaks under Voila. Being in a kernel must NOT produce a prefix on its own.
    """
    monkeypatch.setenv("JPY_SESSION_NAME", "a-session")
    monkeypatch.setenv("JUPYTERHUB_SERVICE_PREFIX", "/user/alice/")

    assert get_default_client_prefix() is None


def test_the_environment_sets_a_manual_prefix(monkeypatch):
    monkeypatch.setenv("VECTORTILESERVER_CLIENT_PREFIX", "/custom/{port}")

    assert get_default_client_prefix() == "/custom/{port}"


def test_an_empty_environment_value_forces_the_loopback_url(monkeypatch):
    monkeypatch.setenv("VECTORTILESERVER_CLIENT_PREFIX", "")

    assert get_default_client_prefix() is None


# --------------------------------------------------------------------------- #
# URL construction                                                              #
# --------------------------------------------------------------------------- #


def test_the_url_is_a_loopback_url_by_default(client):
    assert client.client_prefix is None
    assert client.pmtiles_url.startswith(f"http://127.0.0.1:{client.server_port}/pmtiles?filePath=")


def test_a_manual_prefix_is_used_in_the_url(pmtiles_file, monkeypatch):
    monkeypatch.setenv("VECTORTILESERVER_CLIENT_PREFIX", "/proxy/{port}")

    client = TileClient(data_source=pmtiles_file, allowed_directories=[pmtiles_file.parent])

    prefix = f"/proxy/{client.server_port}"
    assert client.client_prefix == prefix
    assert client.pmtiles_url == f"{prefix}/pmtiles?filePath={client.pmtiles_path}"


def test_the_tile_url_always_ends_in_pmtiles(client, pmtiles_file, monkeypatch):
    """
    protomaps-leaflet picks its PMTiles reader with `url.endsWith(".pmtiles")`.
    Move `filePath` off the end of the query string and tiles stop loading in the
    browser with nothing failing on the Python side.
    """
    assert client.pmtiles_url.endswith(".pmtiles")

    monkeypatch.setenv("VECTORTILESERVER_CLIENT_PREFIX", "/proxy/{port}")
    proxied = TileClient(data_source=pmtiles_file, allowed_directories=[pmtiles_file.parent])
    assert proxied.pmtiles_url.endswith(".pmtiles")


def test_a_full_url_prefix_is_not_mangled(pmtiles_file, monkeypatch):
    """A reverse-proxy prefix that is already a URL must not become `/https://…`."""
    monkeypatch.setenv("VECTORTILESERVER_CLIENT_PREFIX", "https://tiles.example.org/proxy/{port}/")

    client = TileClient(data_source=pmtiles_file, allowed_directories=[pmtiles_file.parent])

    assert client.client_base_url == f"https://tiles.example.org/proxy/{client.server_port}"


def test_awkward_characters_in_the_path_are_encoded(tmp_path):
    """`#` would truncate the query string, `&` would split it, spaces are invalid."""
    from conftest import write_minimal_pmtiles

    source = write_minimal_pmtiles(tmp_path / "my map #1 & more.pmtiles")
    client = TileClient(data_source=source, allowed_directories=[tmp_path])

    assert "%23" in client.pmtiles_url and "%26" in client.pmtiles_url
    assert " " not in client.pmtiles_url
    assert client.pmtiles_url.endswith(".pmtiles")  # protomaps still sees the suffix


def test_the_layer_recovers_the_path_it_was_given(tmp_path):
    pytest.importorskip("ipyleaflet")
    from conftest import write_minimal_pmtiles

    source = write_minimal_pmtiles(tmp_path / "my map #1 & more.pmtiles")
    client = TileClient(data_source=source, allowed_directories=[tmp_path])

    layer = client.create_leaflet_layer()

    assert layer.pmtiles_path == str(client.pmtiles_path)


def test_server_port_exposes_the_loopback_port(client):
    assert isinstance(client.server_port, int)
    assert client.server_port == client.port


# --------------------------------------------------------------------------- #
# Range fidelity through the comm bridge                                        #
# --------------------------------------------------------------------------- #


def test_range_requests_survive_the_comm_bridge(client):
    """
    The acceptance criterion from issue #3, on the kernel side: the bridge must
    forward the `Range` request header and hand back `206` plus `Content-Range`.
    Without this PMTiles cannot be read at all through the bridge.
    """
    bridge_proxy = pytest.importorskip("jupyter_loopback._bridge_proxy")

    result, buffers = bridge_proxy._builtin_fetch(
        {
            "port": client.server_port,
            "path": "/pmtiles",
            "query": {"filePath": str(client.pmtiles_path)},
            "method": "GET",
            "headers": {"Range": "bytes=0-127"},
        },
        [],
    )

    headers = {name.lower(): value for name, value in result["headers"]}

    assert result["code"] == 206
    assert headers["content-range"].startswith("bytes 0-127/")
    assert headers["accept-ranges"] == "bytes"
    assert len(buffers[0]) == 128


# --------------------------------------------------------------------------- #
# Bridge installation                                                           #
# --------------------------------------------------------------------------- #


class FakeLoopback:
    """Stand-in for the jupyter_loopback module."""

    def __init__(self):
        self.enabled = False
        self.calls = []

    def is_comm_bridge_enabled(self):
        return self.enabled

    def enable_comm_bridge(self):
        self.enabled = True

    def intercept_localhost(self, port, *, path_prefix=None):
        self.calls.append((port, path_prefix))


@pytest.fixture
def fake_loopback(monkeypatch):
    fake = FakeLoopback()
    monkeypatch.setitem(sys.modules, "jupyter_loopback", fake)
    monkeypatch.setattr(bridge, "_INTERCEPTED", set())
    return fake


def test_the_bridge_is_installed_once_per_port(fake_loopback):
    """Ten layers on one port must not emit ten shims."""
    bridge.enable_for_port(4242)
    bridge.enable_for_port(4242)

    assert fake_loopback.enabled
    assert fake_loopback.calls == [(4242, None)]


def test_a_changed_prefix_is_reinstalled(fake_loopback):
    bridge.enable_for_port(4242)
    bridge.enable_for_port(4242, path_prefix="/proxy/4242")

    assert fake_loopback.calls == [(4242, None), (4242, "/proxy/4242")]


def test_a_trailing_slash_is_not_a_different_prefix(fake_loopback):
    bridge.enable_for_port(4242, path_prefix="/proxy/4242")
    bridge.enable_for_port(4242, path_prefix="/proxy/4242/")

    assert fake_loopback.calls == [(4242, "/proxy/4242")]


def test_the_bridge_can_be_disabled(fake_loopback, monkeypatch):
    monkeypatch.setenv("VECTORTILESERVER_DISABLE_JUPYTER_LOOPBACK", "1")

    bridge.enable_for_port(4242)

    assert fake_loopback.calls == []


def test_a_missing_port_is_a_no_op(fake_loopback):
    bridge.enable_for_port(None)

    assert fake_loopback.calls == []


def test_a_broken_bridge_does_not_break_layer_creation(monkeypatch, caplog):
    """
    Layer construction degrades to "tiles fail", never to "this raises" — but it
    says so, because the symptom is otherwise indistinguishable from silence.
    """

    class Broken:
        def is_comm_bridge_enabled(self):
            raise RuntimeError("anywidget is having a bad day")

    monkeypatch.setitem(sys.modules, "jupyter_loopback", Broken())
    monkeypatch.setattr(bridge, "_INTERCEPTED", set())
    monkeypatch.setattr(bridge, "_warned_failure", False)

    with caplog.at_level("WARNING"):
        bridge.enable_for_port(4242)
        bridge.enable_for_port(4243)

    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1  # warned, but only once
    assert "anywidget is having a bad day" in warnings[0].message


def test_the_real_bridge_is_safe_outside_a_notebook(client):
    """
    Exercises the actual jupyter_loopback install, not a fake. Outside a kernel
    there is no frontend to talk to, and enabling the bridge has to stay a quiet
    no-op rather than taking the layer down with it.
    """
    pytest.importorskip("jupyter_loopback")

    client.enable_jupyter_loopback()
    client.enable_jupyter_loopback()  # idempotent


def test_creating_a_layer_bridges_the_port(client, monkeypatch):
    pytest.importorskip("ipyleaflet")

    bridged = []
    monkeypatch.setattr(
        "vectortileserver.client.enable_for_port",
        lambda port, *, path_prefix=None: bridged.append((port, path_prefix)),
    )

    client.create_leaflet_layer()

    assert bridged == [(client.server_port, None)]
