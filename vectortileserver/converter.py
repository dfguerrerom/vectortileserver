"""
Converter component for the Vector Tile Server package.

This module provides functionality to convert vector data to PMTiles format.
"""

import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Union

import geopandas as gpd

logger = logging.getLogger(__name__)

#: Tippecanoe options applied unless the caller overrides them.
#:
#: Tippecanoe is tuned for basemaps: below its computed base zoom it keeps only
#: ``1 / drop_rate`` of the features per level (2.5 by default), and it discards
#: whatever else is needed to stay under 200k features and 500KB per tile. For a
#: point layer that is silent data loss — 5000 points render as 1 at zoom 0 — and
#: this package exists to show analysis point sets truthfully, so retention wins
#: over tile size here. Pass ``no_feature_limit=False`` (or any other key) through
#: ``conversion_options`` to get tippecanoe's behaviour back.
DEFAULT_CONVERSION_OPTIONS: Dict[str, Any] = {
    "drop_rate": 1,
    "no_feature_limit": True,
    "no_tile_size_limit": True,
}

_TIPPECANOE_INSTALL_HINT = (
    "Install it from https://github.com/felt/tippecanoe or with "
    "`conda install -c conda-forge tippecanoe`."
)


class TileConverter:
    """
    Converts vector data to PMTiles format using Tippecanoe or other methods.
    """

    def __init__(
        self,
        input_path: Union[str, Path],
        output_path: Union[str, Path] | None = None,
        tippecanoe_path: str = "tippecanoe",
    ):
        """
        Initialize the tile converter.

        Args:
            input_path: Path to the input vector data
            output_path: Directory to write the output PMTiles file into
            tippecanoe_path: Path to the tippecanoe executable
        """
        self.input_path = Path(input_path)
        self.output_path = (
            Path(output_path) if output_path else self.input_path.with_suffix(".tiles")
        )
        self.tippecanoe_path = tippecanoe_path

        # Validate input file existence
        if not self.input_path.exists():
            raise FileNotFoundError(f"Input file not found: {self.input_path}")

    @property
    def pmtiles_path(self) -> Path:
        """Path of the PMTiles file this converter writes."""
        return self.output_path / f"{self.input_path.stem}.pmtiles"

    def convert(
        self,
        method: str = "auto",
        max_zoom: int = 14,
        min_zoom: int = 0,
        **kwargs,
    ) -> Path:
        """
        Convert the input data to PMTiles.

        Args:
            method: Accepted for backwards compatibility and ignored — tippecanoe
                is the only backend. Named explicitly (rather than left to
                ``**kwargs``) so a caller passing it does not turn into an
                unsupported ``--method`` flag on the tippecanoe command line.
            max_zoom: Maximum zoom level
            min_zoom: Minimum zoom level
            **kwargs: Additional tippecanoe options, overriding
                :data:`DEFAULT_CONVERSION_OPTIONS`. Keys become long flags
                (``no_feature_limit`` -> ``--no-feature-limit``), single
                characters become short ones. ``True`` renders a bare flag;
                ``False`` and ``None`` drop the flag entirely.

        Returns:
            Path: Path to the output PMTiles file
        """
        self.output_path.mkdir(parents=True, exist_ok=True)
        pmtiles_path = self.pmtiles_path

        # Non-GeoJSON inputs are transcoded into a scratch directory rather than
        # next to the source: writing `<stem>.geojson` beside a shapefile would
        # silently overwrite a file the user may already have there.
        with tempfile.TemporaryDirectory(prefix="vectortileserver-") as tmpdir:
            geojson_path = self._ensure_geojson(self.input_path, Path(tmpdir))
            cmd = self._build_command(pmtiles_path, geojson_path, max_zoom, min_zoom, kwargs)

            logger.debug(f"Running command: {' '.join(cmd)}")

            try:
                result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            except FileNotFoundError as e:
                raise RuntimeError(
                    f"Tippecanoe executable not found: {self.tippecanoe_path!r}. "
                    f"{_TIPPECANOE_INSTALL_HINT}"
                ) from e
            except subprocess.CalledProcessError as e:
                logger.error(f"Tippecanoe error: {e.stderr}")
                raise RuntimeError(f"Tippecanoe conversion failed: {e.stderr}") from e

            logger.debug(f"Tippecanoe output: {result.stdout}")

        return pmtiles_path

    def _build_command(
        self,
        pmtiles_path: Path,
        geojson_path: Path,
        max_zoom: int,
        min_zoom: int,
        options: Dict[str, Any],
    ) -> List[str]:
        """
        Build the tippecanoe invocation for a single conversion.

        Split out from :meth:`convert` so flag handling stays testable without
        tippecanoe installed.
        """
        cmd = [
            self.tippecanoe_path,
            "-o",
            str(pmtiles_path),
            "-z",
            str(max_zoom),
            "-Z",
            str(min_zoom),
            "-l",
            self.input_path.stem,
            "--force",  # Overwrite existing files
        ]

        for key, value in {**DEFAULT_CONVERSION_OPTIONS, **options}.items():
            # Falsy flags are dropped, not rendered as `--flag False`; that is
            # what lets a caller switch one of the defaults back off.
            if value is False or value is None:
                continue

            if len(key) == 1:
                cmd.append(f"-{key}")
            else:
                cmd.append(f"--{key.replace('_', '-')}")

            if value is not True:  # Only add value if it's not a boolean flag
                cmd.append(str(value))

        cmd.append(str(geojson_path))

        return cmd

    def _ensure_geojson(self, input_path: Path, workdir: Path) -> Path:
        """
        Ensure the input file is in GeoJSON format, converting if necessary.

        Args:
            input_path: Path to the input file
            workdir: Scratch directory for the converted copy

        Returns:
            Path: Path to the GeoJSON file
        """
        # If already GeoJSON, return as is
        if input_path.suffix.lower() in (".geojson", ".json"):
            return input_path

        # Convert to GeoJSON
        logger.debug(f"Converting {input_path} to GeoJSON")
        gdf = gpd.read_file(input_path)

        geojson_path = workdir / f"{input_path.stem}.geojson"
        gdf.to_file(geojson_path, driver="GeoJSON")

        return geojson_path
