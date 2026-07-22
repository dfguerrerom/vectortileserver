from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vectortileserver.client import TileClient

__title__ = "vectortileserver"
__summary__ = "Local vector tile server for visualizing PMTiles in Jupyter"
__version__ = "0.1.0"

__author__ = "Daniel Guerrero"
__email__ = "dfgm2006@gmail.com"

__license__ = "MIT"

__all__ = ["TileClient"]


def __getattr__(name: str):
    """
    Expose TileClient lazily.

    Importing it eagerly would drag geopandas and ipyleaflet into every process
    that merely imports this package (e.g. to read ``__version__``); the lazy
    hook keeps a bare ``import vectortileserver`` cheap.
    """
    if name == "TileClient":
        from vectortileserver.client import TileClient

        return TileClient

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
