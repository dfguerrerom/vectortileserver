"""
Vector -> PMTiles conversion.

This whole path was broken in 0.1.0 and no test noticed: `convert()` returned the
output *directory*, so `TileClient` handed a directory to `open()`. See issue #2.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import count_tile_features, write_points

from vectortileserver.client import (
    TileClient,
    _cache_key_options,
    _read_conversion_options,
    _source_mtime,
    _write_conversion_options,
)
from vectortileserver.converter import TileConverter, _resolve_tippecanoe

requires_tippecanoe = pytest.mark.skipif(
    shutil.which("tippecanoe") is None, reason="tippecanoe is not installed"
)


# --------------------------------------------------------------------------- #
# Command building — runs without tippecanoe installed                          #
# --------------------------------------------------------------------------- #


def build_command(tmp_path: Path, **options) -> list:
    source = write_points(tmp_path / "pts.geojson")
    converter = TileConverter(source, tmp_path)
    return converter._build_command(tmp_path / "pts.pmtiles", source, 14, 0, options)


def test_retention_flags_are_applied_by_default(tmp_path):
    cmd = build_command(tmp_path)

    assert "--drop-rate" in cmd
    assert cmd[cmd.index("--drop-rate") + 1] == "1"
    assert "--no-feature-limit" in cmd
    assert "--no-tile-size-limit" in cmd


def test_options_override_the_defaults(tmp_path):
    cmd = build_command(tmp_path, drop_rate=2.5)

    assert cmd[cmd.index("--drop-rate") + 1] == "2.5"
    assert cmd.count("--drop-rate") == 1


def test_false_options_drop_the_flag_entirely(tmp_path):
    cmd = build_command(tmp_path, no_feature_limit=False, no_tile_size_limit=None)

    assert "--no-feature-limit" not in cmd
    assert "--no-tile-size-limit" not in cmd
    assert "False" not in cmd  # not rendered as `--no-feature-limit False`


def test_single_character_options_become_short_flags(tmp_path):
    cmd = build_command(tmp_path, B=5)

    assert "-B" in cmd
    assert cmd[cmd.index("-B") + 1] == "5"


def test_missing_tippecanoe_is_reported_actionably(tmp_path):
    source = write_points(tmp_path / "pts.geojson")
    converter = TileConverter(source, tmp_path, tippecanoe_path="tippecanoe-does-not-exist")

    with pytest.raises(RuntimeError, match="not found"):
        converter.convert()


# --------------------------------------------------------------------------- #
# tippecanoe resolution — bare name that isn't on PATH                          #
# --------------------------------------------------------------------------- #


def test_resolve_tippecanoe_keeps_an_explicit_path():
    # An explicit path is never second-guessed, even if it isn't on PATH.
    assert _resolve_tippecanoe("/opt/x/tippecanoe") == "/opt/x/tippecanoe"


def test_resolve_tippecanoe_falls_back_to_interpreter_sibling(monkeypatch, tmp_path):
    # A venv launched by absolute path (a Jupyter kernel, say) has tippecanoe in
    # bin/ but not on PATH -> resolve it next to sys.executable.
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "tippecanoe").write_text("")
    monkeypatch.setattr(shutil, "which", lambda *_: None)
    monkeypatch.setattr(sys, "executable", str(bindir / "python3"))

    assert _resolve_tippecanoe("tippecanoe") == str(bindir / "tippecanoe")


def test_resolve_tippecanoe_unchanged_when_no_sibling(monkeypatch, tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()  # no tippecanoe here
    monkeypatch.setattr(shutil, "which", lambda *_: None)
    monkeypatch.setattr(sys, "executable", str(bindir / "python3"))

    # Nothing to resolve to -> return the bare name so the actionable error fires.
    assert _resolve_tippecanoe("tippecanoe") == "tippecanoe"


def test_build_command_uses_the_resolved_tippecanoe(monkeypatch, tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "tippecanoe").write_text("")
    monkeypatch.setattr(shutil, "which", lambda *_: None)
    monkeypatch.setattr(sys, "executable", str(bindir / "python3"))

    assert build_command(tmp_path)[0] == str(bindir / "tippecanoe")


def test_data_source_is_required():
    with pytest.raises(ValueError, match="data_source is required"):
        TileClient()


def test_method_argument_never_reaches_the_command(tmp_path, monkeypatch):
    """
    Regression: `method` was a documented convert() parameter. Dropping it sent
    method=... through **kwargs and rendered `--method auto`, which tippecanoe
    rejects. It must be absorbed, not forwarded.
    """
    source = write_points(tmp_path / "pts.geojson")
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        raise subprocess.CalledProcessError(1, cmd, stderr="stopped before running")

    monkeypatch.setattr("vectortileserver.converter.subprocess.run", fake_run)

    with pytest.raises(RuntimeError):
        TileConverter(source, tmp_path).convert(method="auto")

    assert "--method" not in captured["cmd"]


# --------------------------------------------------------------------------- #
# Cache identity — sidecar and shapefile freshness (run without tippecanoe)     #
# --------------------------------------------------------------------------- #


def test_missing_or_corrupt_sidecar_reads_as_unknown(tmp_path):
    """A None result is what forces regeneration of archives we can't vouch for."""
    pmtiles = tmp_path / "x.pmtiles"
    pmtiles.write_bytes(b"")

    assert _read_conversion_options(pmtiles) is None  # no sidecar (e.g. built by 0.1.0)

    (tmp_path / "x.pmtiles.json").write_text("{ not valid json")
    assert _read_conversion_options(pmtiles) is None  # corrupt

    _write_conversion_options(pmtiles, {"drop_rate": 1})
    assert _read_conversion_options(pmtiles) == {"drop_rate": 1}  # round-trips


def test_source_mtime_spans_the_shapefile_dataset(tmp_path):
    for ext in (".shp", ".shx", ".dbf", ".prj"):
        (tmp_path / f"d{ext}").write_text("x")
    os.utime(tmp_path / "d.shp", (1000, 1000))
    os.utime(tmp_path / "d.shx", (1500, 1500))
    os.utime(tmp_path / "d.prj", (2000, 2000))
    os.utime(tmp_path / "d.dbf", (5000, 5000))  # newest companion

    assert _source_mtime(tmp_path / "d.shp") == 5000

    # a same-stem file that is not a shapefile companion is not part of the dataset
    (tmp_path / "d.geojson").write_text("x")
    os.utime(tmp_path / "d.geojson", (9000, 9000))
    assert _source_mtime(tmp_path / "d.shp") == 5000

    # single-file sources just use their own mtime
    single = tmp_path / "pts.geojson"
    single.write_text("x")
    os.utime(single, (7000, 7000))
    assert _source_mtime(single) == 7000


# --------------------------------------------------------------------------- #
# Real conversions                                                              #
# --------------------------------------------------------------------------- #


@requires_tippecanoe
def test_convert_returns_the_file_not_the_directory(tmp_path):
    """The exact regression from issue #2, at its source."""
    source = write_points(tmp_path / "pts.geojson")

    result = TileConverter(source, tmp_path).convert()

    assert result.is_file()
    assert result == tmp_path / "pts.pmtiles"


@requires_tippecanoe
def test_tile_client_converts_a_geojson_end_to_end(tmp_path):
    """The reproduction from issue #2 — used to raise IsADirectoryError."""
    source = write_points(tmp_path / "pts.geojson")

    client = TileClient(data_source=source, allowed_directories=[tmp_path])

    assert client.pmtiles_path.is_file()
    assert client.pmtiles_path == tmp_path / "pts.pmtiles"
    assert client.list_layers() == ["pts"]
    assert client.bounds["left"] == pytest.approx(0, abs=0.01)


@requires_tippecanoe
def test_every_point_survives_at_zoom_zero(tmp_path):
    """
    R2: an accuracy assessment cannot silently lose points.

    Tippecanoe's basemap defaults collapse these 200 points to 1 at zoom 0.
    """
    source = write_points(tmp_path / "pts.geojson", count=200)

    retained = TileClient(data_source=source, allowed_directories=[tmp_path])
    assert count_tile_features(retained.pmtiles_path, 0, 0, 0) == 200

    # And callers can still ask for tippecanoe's thinning back. Deliberately the
    # same source file: asking for different options has to rebuild rather than
    # serve the archive the previous client just wrote.
    thinned = TileClient(
        data_source=source,
        allowed_directories=[tmp_path],
        conversion_options={"drop_rate": 2.5},
    )
    assert count_tile_features(thinned.pmtiles_path, 0, 0, 0) < 200


@requires_tippecanoe
def test_conversion_does_not_clobber_a_sibling_geojson(tmp_path):
    """Transcoding a shapefile used to overwrite `<stem>.geojson` next to it."""
    geopandas = pytest.importorskip("geopandas")
    shapely = pytest.importorskip("shapely.geometry")

    frame = geopandas.GeoDataFrame(
        {"map_code": [1, 2]},
        geometry=[shapely.Point(0, 0), shapely.Point(0.001, 0.001)],
        crs="EPSG:4326",
    )
    frame.to_file(tmp_path / "data.shp")

    precious = tmp_path / "data.geojson"
    precious.write_text('{"keep": "me"}')

    TileClient(data_source=tmp_path / "data.shp", allowed_directories=[tmp_path])

    assert precious.read_text() == '{"keep": "me"}'


# --------------------------------------------------------------------------- #
# Reuse of previously converted archives                                        #
# --------------------------------------------------------------------------- #


@requires_tippecanoe
def test_an_unrelated_pmtiles_does_not_block_conversion(tmp_path):
    """
    Any leftover .pmtiles in the directory used to short-circuit the lookup and
    leave `pmtiles_path` unset, surfacing as a confusing ValueError.
    """
    (tmp_path / "leftover.pmtiles").write_bytes(b"not a real archive")
    source = write_points(tmp_path / "pts.geojson")

    client = TileClient(data_source=source, allowed_directories=[tmp_path])

    assert client.pmtiles_path == tmp_path / "pts.pmtiles"


@requires_tippecanoe
def test_a_stale_pmtiles_is_regenerated(tmp_path):
    source = write_points(tmp_path / "pts.geojson", count=10)
    first = TileClient(data_source=source, allowed_directories=[tmp_path])

    # Rewrite the source with more points and mark it newer than the archive.
    write_points(source, count=40, seed=1)
    os.utime(first.pmtiles_path, (1_000_000, 1_000_000))
    os.utime(source, (2_000_000, 2_000_000))

    second = TileClient(data_source=source, allowed_directories=[tmp_path])

    assert second.pmtiles_path.stat().st_mtime > 1_000_000
    assert count_tile_features(second.pmtiles_path, 0, 0, 0) == 40


@requires_tippecanoe
def test_an_up_to_date_pmtiles_is_reused(tmp_path):
    source = write_points(tmp_path / "pts.geojson")
    first = TileClient(data_source=source, allowed_directories=[tmp_path])

    os.utime(source, (1_000_000, 1_000_000))
    os.utime(first.pmtiles_path, (2_000_000, 2_000_000))

    second = TileClient(data_source=source, allowed_directories=[tmp_path])

    assert second.pmtiles_path.stat().st_mtime == 2_000_000


@requires_tippecanoe
def test_changed_options_rebuild_even_when_the_archive_is_fresh(tmp_path):
    """
    The options are part of the archive's identity. An mtime-only check serves
    the previous build, so `conversion_options` looks silently ignored.
    """
    source = write_points(tmp_path / "pts.geojson")
    first = TileClient(data_source=source, allowed_directories=[tmp_path])
    os.utime(source, (1_000_000, 1_000_000))
    os.utime(first.pmtiles_path, (2_000_000, 2_000_000))

    second = TileClient(
        data_source=source,
        allowed_directories=[tmp_path],
        conversion_options={"max_zoom": 6},
    )

    assert second.pmtiles_path.stat().st_mtime != 2_000_000


@requires_tippecanoe
def test_the_same_options_still_reuse_the_archive(tmp_path):
    """Rebuilding on *changed* options must not mean rebuilding every time."""
    options = {"drop_rate": 2.5}
    source = write_points(tmp_path / "pts.geojson")
    first = TileClient(source, allowed_directories=[tmp_path], conversion_options=options)
    os.utime(source, (1_000_000, 1_000_000))
    os.utime(first.pmtiles_path, (2_000_000, 2_000_000))

    second = TileClient(source, allowed_directories=[tmp_path], conversion_options=dict(options))

    assert second.pmtiles_path.stat().st_mtime == 2_000_000


@requires_tippecanoe
def test_a_legacy_archive_without_a_sidecar_is_regenerated(tmp_path):
    """
    A pre-sidecar archive may have been built with point-dropping defaults.
    Reusing it just because its mtime is fresh would silently keep those dropped
    points; the missing sidecar must force a rebuild under current settings.
    """
    source = write_points(tmp_path / "pts.geojson", count=200)

    # Simulate a 0.1.0 conversion: tippecanoe's thinning defaults, no sidecar.
    legacy = tmp_path / "pts.pmtiles"
    subprocess.run(
        [
            "tippecanoe",
            "-o",
            str(legacy),
            "-z",
            "14",
            "-Z",
            "0",
            "-l",
            "pts",
            "--force",
            str(source),
        ],
        check=True,
        capture_output=True,
    )
    os.utime(legacy, (os.stat(source).st_mtime + 10,) * 2)  # cache newer than source
    assert not (tmp_path / "pts.pmtiles.json").exists()
    assert count_tile_features(legacy, 0, 0, 0) < 200  # thinned

    client = TileClient(source, allowed_directories=[tmp_path])

    assert (tmp_path / "pts.pmtiles.json").exists()  # sidecar written on regeneration
    assert count_tile_features(client.pmtiles_path, 0, 0, 0) == 200  # retention applied


@requires_tippecanoe
def test_a_corrupt_sidecar_forces_regeneration(tmp_path):
    source = write_points(tmp_path / "pts.geojson")
    first = TileClient(source, allowed_directories=[tmp_path])

    (tmp_path / "pts.pmtiles.json").write_text("{ truncated")
    os.utime(source, (500_000, 500_000))
    os.utime(first.pmtiles_path, (1_000_000, 1_000_000))

    second = TileClient(source, allowed_directories=[tmp_path])

    assert second.pmtiles_path.stat().st_mtime != 1_000_000  # rebuilt
    assert json.loads((tmp_path / "pts.pmtiles.json").read_text())["options"] == {}


@requires_tippecanoe
def test_convert_still_accepts_the_legacy_method_argument(tmp_path):
    source = write_points(tmp_path / "pts.geojson")

    result = TileConverter(source, tmp_path).convert(method="auto")

    assert result.is_file()


@requires_tippecanoe
def test_editing_shapefile_attributes_invalidates_the_cache(tmp_path):
    """The .shp can be untouched while the .dbf attributes change under it."""
    geopandas = pytest.importorskip("geopandas")
    shapely = pytest.importorskip("shapely.geometry")

    geopandas.GeoDataFrame(
        {"map_code": [1, 2]},
        geometry=[shapely.Point(0, 0), shapely.Point(0.001, 0.001)],
        crs="EPSG:4326",
    ).to_file(tmp_path / "data.shp")
    first = TileClient(tmp_path / "data.shp", allowed_directories=[tmp_path])

    # Cache is newer than the .shp, but the .dbf changed afterwards.
    os.utime(tmp_path / "data.shp", (500_000, 500_000))
    os.utime(first.pmtiles_path, (1_000_000, 1_000_000))
    os.utime(tmp_path / "data.dbf", (2_000_000, 2_000_000))

    assert not first._can_reuse(first.pmtiles_path)


# --------------------------------------------------------------------------- #
# Temporary directory                                                           #
# --------------------------------------------------------------------------- #


def test_scratch_defaults_to_the_output_directory(tmp_path):
    source = write_points(tmp_path / "pts.geojson")
    out = tmp_path / "tiles"

    assert TileConverter(source, out).scratch_dir == out


def test_temp_dir_overrides_the_scratch_location(tmp_path):
    source = write_points(tmp_path / "pts.geojson")
    scratch = tmp_path / "fast"

    assert TileConverter(source, tmp_path, temp_dir=scratch).scratch_dir == scratch


def test_tippecanoe_is_told_where_to_scratch(tmp_path):
    """$TMPDIR does not reach tippecanoe, so the flag is the only way to move its
    temporary files off a slow /tmp."""
    cmd = build_command(tmp_path)

    assert "--temporary-directory" in cmd
    assert cmd[cmd.index("--temporary-directory") + 1] == str(tmp_path)


def test_caller_can_redirect_the_scratch_flag(tmp_path):
    cmd = build_command(tmp_path, temporary_directory="/somewhere/fast")

    assert cmd.count("--temporary-directory") == 1
    assert cmd[cmd.index("--temporary-directory") + 1] == "/somewhere/fast"


def test_scratch_flag_can_be_switched_off(tmp_path):
    """Opting back into tippecanoe's own default, like the other overridable flags."""
    cmd = build_command(tmp_path, temporary_directory=False)

    assert "--temporary-directory" not in cmd


def test_scratch_location_is_not_part_of_the_archive_identity(tmp_path):
    """Otherwise a per-run temporary directory reconverts on every run."""
    recorded = _cache_key_options({"drop_rate": 1, "temporary_directory": "/tmp/somewhere"})

    assert recorded == {"drop_rate": 1}


@requires_tippecanoe
def test_scratching_into_the_output_directory_leaves_only_the_archive(tmp_path):
    """The default puts the temporary files where the output goes, so they must be cleaned up."""
    source = write_points(tmp_path / "pts.geojson")
    out = tmp_path / "tiles"

    pmtiles_path = TileConverter(source, out).convert()

    assert pmtiles_path.exists()
    assert sorted(p.name for p in out.iterdir()) == ["pts.pmtiles"]


@requires_tippecanoe
def test_changing_only_the_scratch_dir_reuses_the_archive(tmp_path):
    source = write_points(tmp_path / "pts.geojson")
    first = TileClient(
        source,
        allowed_directories=[tmp_path],
        conversion_options={"temporary_directory": str(tmp_path)},
    )
    os.utime(source, (1_000_000, 1_000_000))
    os.utime(first.pmtiles_path, (2_000_000, 2_000_000))

    scratch = tmp_path / "elsewhere"
    scratch.mkdir()
    second = TileClient(
        source,
        allowed_directories=[tmp_path],
        conversion_options={"temporary_directory": str(scratch)},
    )

    assert second.pmtiles_path.stat().st_mtime == 2_000_000
