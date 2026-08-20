from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vectortileserver.client import TileClient

__title__ = "vectortileserver"
__summary__ = "Local vector tile server for visualizing PMTiles in Jupyter"
__version__ = "0.3.0"

__author__ = "Daniel Guerrero"
__email__ = "dfgm2006@gmail.com"

__license__ = "MIT"

__all__ = [  # noqa: RUF022 (grouped by module, matching _LAZY below)
    "TileClient",
    "VectorTileLayer",
    "TileWorkspace",
    "default_workspace",
    "open",
    "open_async",
    "open_many",
    "default_style",
    "categorized_style",
    "single_symbol_style",
]

_LAZY = {
    "TileClient": "vectortileserver.client",
    "VectorTileLayer": "vectortileserver.pmtiles_layer",
    "TileWorkspace": "vectortileserver.workspace",
    "default_workspace": "vectortileserver.workspace",
    "open": "vectortileserver.workspace",
    "open_async": "vectortileserver.workspace",
    "open_many": "vectortileserver.workspace",
    "default_style": "vectortileserver.styles",
    "categorized_style": "vectortileserver.styles",
    "single_symbol_style": "vectortileserver.styles",
}


def __getattr__(name: str):
    """Expose the public surface lazily so a bare ``import vectortileserver`` does
    not drag in ipyleaflet / geopandas (the jupyter-server process imports this
    module and needs neither)."""
    module = _LAZY.get(name)
    if module is not None:
        import importlib

        obj = getattr(importlib.import_module(module), name)
        # importlib binds the submodule as a package attribute; caching the
        # resolved object here keeps it from being shadowed by a submodule
        # whose leaf name matches an export.
        globals()[name] = obj
        return obj
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
