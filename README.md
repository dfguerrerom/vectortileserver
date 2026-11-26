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
pip install "vectortileserver[leaflet]"   # converter + server + ipyleaflet layers
pip install vectortileserver              # converter + server only
```

The `leaflet` extra brings `ipyleaflet` and the server-side click query (`get_data_from_coords`). Leave it out when the map is drawn by something that reads PMTiles in the browser itself, such as MapLibre: the archive's URL is all that frontend needs.

## Demo

[`examples/demo.ipynb`](examples/demo.ipynb) builds a point layer end to end and doubles as a bridge test. Open it in JupyterLab, or serve it with Voila to confirm tiles load in a sandboxed webview (watch the Network tab for the absence of direct `127.0.0.1` requests):

```bash
jupyter lab examples/demo.ipynb
voila examples/demo.ipynb
```

## Usage

With the `leaflet` extra:

```python
from ipyleaflet import Map
from vectortileserver import TileClient

client = TileClient("points.geojson")   # converts to points.pmtiles
m = Map(center=client.center, zoom=10)
m.add(client.create_leaflet_layer())
m
```

A conversion is reused as long as the `.pmtiles` file is at least as new as its source *and* was built with the same `conversion_options` — the options are recorded in a `<name>.pmtiles.json` sidecar. Edit the source or change the options and the next `TileClient` reconverts. Delete the `.pmtiles` to force a rebuild.

## Workspace API (recommended)

```python
import vectortileserver as vts

archive = await vts.open_async("data.geojson")   # convert off-thread, then serve
archive.url            # what the browser fetches
archive.layers         # vector layer ids, e.g. ("data",)
archive.bounds         # [[S, W], [N, E]], or None for a point/degenerate archive
```

`open` / `open_async` / `open_many` return a `TileArchive`, which needs no map
library. Its port is already bridged to the browser (see [Notebook
frontends](#notebook-frontends)), so `url` can go straight to a MapLibre
`pmtiles://` source. For ipyleaflet, build a layer from it, which needs the
`leaflet` extra:

```python
from ipyleaflet import Map

m = Map()
layer = archive.create_leaflet_layer()          # a VectorTileLayer (ipyleaflet PMTilesLayer)
m.add(layer)
if layer.bounds:
    m.fit_bounds(layer.bounds)                   # zoom to the layer's own bounds

# many datasets, in parallel:
for archive in await vts.open_many(["a.geojson", "b.shp"]):
    m.add(archive.create_leaflet_layer())
bounds = vts.default_workspace().bounds()        # union of everything opened (None if none bounded)
if bounds:
    m.fit_bounds(bounds)
```

`create_leaflet_layer` takes a style, either a builder (`vts.default_style`,
`vts.single_symbol_style(color=...)`, `vts.categorized_style(field, values)`) or a
full MapLibre style dict. Restyle by swapping `layer.with_style(...)`. Building
a layer is cheap and never reconverts. For advanced control (explicit lifecycle,
isolation), construct a `vts.TileWorkspace`. The classic `TileClient` API keeps
working unchanged.

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

Tiles are fetched by the *browser*, which in many frontends cannot reach the kernel's `http://localhost:<port>` directly. `vectortileserver` tunnels them over the kernel's own comm channel with [`jupyter-loopback`](https://github.com/banesullivan/jupyter-loopback): `open()` and `create_leaflet_layer()` install the bridge automatically (once per port), and the same path works in JupyterLab, Notebook 7, Voila, VS Code Jupyter, and Colab. HTTP Range requests and `206 Partial Content` — what PMTiles relies on — survive the trip.

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
