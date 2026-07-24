# 🌐 vectortileserver

A local vector tile server for visualizing PMTiles in Jupyter — `localtileserver`, but for vectors. Inspired by `localtileserver`, `leafmap`, `protomaps-leaflet` and `maplibre-gl`.

With `TileClient`, you can easily create a local vector tile server to visualize PMTiles in `ipyleaflet`.

If you have a vector file (`.shp`, `.geojson`, `.gpkg`, etc.), `TileClient` will convert it to PMTiles format using `tippecanoe`. If `tippecanoe` is not installed, an error will be raised. However, you can directly visualize local PMTiles as a data source.

## Installation

The quickest way to get everything — the package, its dependencies, and `tippecanoe` — is the bundled conda/micromamba environment:

```bash
micromamba env create -f environment.yml   # or: conda env create -f environment.yml
micromamba activate vectortileserver
```

Or install with pip and provide `tippecanoe` yourself (see [Installing Tippecanoe](#installing-tippecanoe)):

```bash
pip install vectortileserver
```

## Demo

[`examples/demo.ipynb`](examples/demo.ipynb) builds a point layer end to end and doubles as a bridge test. Open it in JupyterLab, or serve it with Voila to confirm tiles load in a sandboxed webview (watch the Network tab for the absence of direct `127.0.0.1` requests):

```bash
jupyter lab examples/demo.ipynb
voila examples/demo.ipynb
```

## Usage

```python
from ipyleaflet import Map
from vectortileserver import TileClient

client = TileClient("points.geojson")   # converts to points.pmtiles
m = Map(center=client.center, zoom=10)
m.add(client.create_leaflet_layer())
m
```

A conversion is reused as long as the `.pmtiles` file is at least as new as its source *and* was built with the same `conversion_options` — the options are recorded in a `<name>.pmtiles.json` sidecar. Edit the source or change the options and the next `TileClient` reconverts. Delete the `.pmtiles` to force a rebuild.

## Layer-first API (recommended)

```python
import vectortileserver as vts
from ipyleaflet import Map

m = Map()
layer = await vts.open_async("data.geojson")   # convert off-thread → ready layer
m.add(layer)
m.fit_bounds(layer.bounds)                      # zoom to the layer's own bounds

# many datasets, in parallel:
for layer in await vts.open_many(["a.geojson", "b.shp"]):
    m.add(layer)
m.fit_bounds(vts.default_workspace().bounds())  # union of everything opened
```

`open_async` runs tippecanoe on a worker thread and returns a `VectorTileLayer`
(an ipyleaflet `PMTilesLayer`) that carries `.bounds` (`[[S,W],[N,E]]`),
`.center`, and `.list_layers()`. Style it with a builder — `vts.default_style`,
`vts.single_symbol_style(color=...)`, or `vts.categorized_style(field, values)` —
and restyle by swapping `layer.with_style(...)`. For advanced control (explicit
lifecycle, isolation), construct a `vts.TileWorkspace`. The classic
`TileClient` API keeps working unchanged.

## Point retention

Tippecanoe is tuned for basemaps: below its computed base zoom it keeps only a fraction of the features per level, and it discards whatever else is needed to stay under 200k features and 500KB per tile. For a point layer that is silent data loss — 200 points can render as 1 at zoom 0.

This package therefore converts with retention on by default:

```
--drop-rate 1 --no-feature-limit --no-tile-size-limit
```

Override any of them through `conversion_options`, which is passed straight to tippecanoe. Keys become flags (`no_feature_limit` → `--no-feature-limit`), `True` renders a bare flag, and `False` or `None` removes it:

```python
# Get tippecanoe's thinning back for a dense layer
TileClient("dense.geojson", conversion_options={"drop_rate": 2.5})

# Or drop a single default
TileClient("dense.geojson", conversion_options={"no_tile_size_limit": False})
```

The defaults live in `vectortileserver.converter.DEFAULT_CONVERSION_OPTIONS`.

## Notebook frontends

Tiles are fetched by the *browser*, which in many frontends cannot reach the kernel's `http://localhost:<port>` directly. `vectortileserver` tunnels them over the kernel's own comm channel with [`jupyter-loopback`](https://github.com/banesullivan/jupyter-loopback): `create_leaflet_layer()` installs the bridge automatically (once per port), and the same path works in JupyterLab, Notebook 7, Voila, SEPAL, VS Code Jupyter, and Colab. HTTP Range requests and `206 Partial Content` — what PMTiles relies on — survive the trip.

| Environment variable | Effect |
| --- | --- |
| `VECTORTILESERVER_DISABLE_JUPYTER_LOOPBACK=1` | Never install the comm bridge. |
| `VECTORTILESERVER_CLIENT_PREFIX` | Route tile URLs through a reverse proxy you run — a root-relative path (`/user/alice/tiles/{port}`) or a full URL (`https://host/tiles/{port}`); `{port}` is substituted. An empty value forces the default `http://localhost:<port>` URLs. |

To bridge a port yourself:

```python
client.server_port                 # the loopback port
client.enable_jupyter_loopback()   # idempotent
```

## Installing Tippecanoe

The bundled `environment.yml` already installs `tippecanoe` from conda-forge, so if you created the environment above you can skip this section.

[Tippecanoe](https://github.com/felt/tippecanoe) is a tool for generating vector tile sets from large collections of GeoJSON features. It is designed to make mapping large datasets easy and efficient.

```bash
git clone https://github.com/felt/tippecanoe.git
cd tippecanoe
make -j
make install
```

Or from conda-forge:

```bash
conda install -c conda-forge tippecanoe
```
