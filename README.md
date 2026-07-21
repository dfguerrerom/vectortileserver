# 🌐 vectortileserver

A local vector tile server for visualizing PMTiles in Jupyter — `localtileserver`, but for vectors. Inspired by `localtileserver`, `leafmap`, `protomaps-leaflet` and `maplibre-gl`.

With `TileClient`, you can easily create a local vector tile server to visualize PMTiles in `ipyleaflet`.

If you have a vector file (`.shp`, `.geojson`, `.gpkg`, etc.), `TileClient` will convert it to PMTiles format using `tippecanoe`. If `tippecanoe` is not installed, an error will be raised. However, you can directly visualize local PMTiles as a data source.

## Usage

```python
from ipyleaflet import Map
from vectortileserver.client import TileClient

client = TileClient("points.geojson")   # converts to points.pmtiles
m = Map(center=client.center, zoom=10)
m.add(client.create_leaflet_layer())
m
```

A conversion is reused as long as the `.pmtiles` file is at least as new as its source *and* was built with the same `conversion_options` — the options are recorded in a `<name>.pmtiles.json` sidecar. Edit the source or change the options and the next `TileClient` reconverts. Delete the `.pmtiles` to force a rebuild.

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

Tiles are fetched by the *browser*, which in many frontends cannot reach the kernel's `http://localhost:<port>`. `vectortileserver` handles this with [`jupyter-loopback`](https://github.com/banesullivan/jupyter-loopback), in two layers:

- A **jupyter-server extension**, enabled on install, proxies `<base_url>/vectortileserver-proxy/<port>/…` to the tile server. This is what JupyterLab, Notebook 7, and JupyterHub use.
- A **comm bridge** tunnels requests over the kernel's comm channel for frontends whose webview is not the jupyter-server origin — Voila, SEPAL, VS Code Jupyter, Colab. `create_leaflet_layer()` installs it automatically, once per port.

Both preserve HTTP Range requests and `206 Partial Content`, which is what PMTiles needs.

| Environment variable | Effect |
| --- | --- |
| `VECTORTILESERVER_DISABLE_JUPYTER_LOOPBACK=1` | Never install the comm bridge. |
| `VECTORTILESERVER_CLIENT_PREFIX` | Override the proxy prefix — a root-relative path (`/user/alice/vectortileserver-proxy/{port}`) or a full URL (`https://host/proxy/{port}`); `{port}` is substituted. Set it to an empty string to force plain `http://localhost:<port>` URLs. |

To bridge a port yourself:

```python
client.server_port                 # the loopback port
client.enable_jupyter_loopback()   # idempotent
```

## Installing Tippecanoe

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
