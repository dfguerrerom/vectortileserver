from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vectortileserver.client import TileClient

__title__ = "vectortileserver"
__summary__ = "Local vector tile server for visualizing PMTiles in Jupyter"
__version__ = "0.1.0"

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
    "fit",
    "union_bounds",
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
    "fit": "vectortileserver.fit",
    "union_bounds": "vectortileserver.fit",
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

        return getattr(importlib.import_module(module), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
