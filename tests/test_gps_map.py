"""Unit tests for GPS map generation from GPX track files."""

from __future__ import annotations

from pathlib import Path

from garmin_analyzer.gps_map import parse_gpx_points, render_gps_map

MOCK_GPX_CONTENT = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="Garmin Connect" xmlns="http://www.topografix.com/GPX/1/1">
  <trk>
    <name>Park Loop</name>
    <type>running</type>
    <trkseg>
      <trkpt lat="48.137" lon="11.575"><ele>520.0</ele></trkpt>
      <trkpt lat="48.138" lon="11.577"><ele>522.0</ele></trkpt>
      <trkpt lat="48.140" lon="11.580"><ele>525.0</ele></trkpt>
      <trkpt lat="48.139" lon="11.582"><ele>524.0</ele></trkpt>
      <trkpt lat="48.137" lon="11.576"><ele>521.0</ele></trkpt>
    </trkseg>
  </trk>
</gpx>
"""


def test_parse_gpx_points(tmp_path: Path):
    gpx_file = tmp_path / "track.gpx"
    gpx_file.write_text(MOCK_GPX_CONTENT, encoding="utf-8")

    points = parse_gpx_points(gpx_file)
    assert len(points) == 5
    assert points[0]["lat"] == 48.137
    assert points[0]["lon"] == 11.575
    assert points[0]["ele"] == 520.0


def test_render_gps_map(tmp_path: Path):
    gpx_file = tmp_path / "track.gpx"
    gpx_file.write_text(MOCK_GPX_CONTENT, encoding="utf-8")

    out_map = tmp_path / "gps_map.png"
    result = render_gps_map(
        gpx_file,
        out_map,
        title="Park Loop",
        distance_km=3.5,
        elevation_gain_m=15.0,
    )

    assert result is not None
    assert out_map.exists()
    assert out_map.stat().st_size > 1000  # valid image file


def test_gpx_to_leaflet_spec(tmp_path: Path):
    from garmin_analyzer.gps_map import generate_leaflet_markdown_block, gpx_to_leaflet_spec

    gpx_file = tmp_path / "track.gpx"
    gpx_file.write_text(MOCK_GPX_CONTENT, encoding="utf-8")

    spec = gpx_to_leaflet_spec(gpx_file, title="Park Loop", distance_km=3.5, elevation_gain_m=15.0)
    assert spec is not None
    assert spec["title"] == "Park Loop"
    assert spec["distance_km"] == 3.5
    assert len(spec["coordinates"]) == 5
    assert spec["coordinates"][0] == [48.137, 11.575]

    block = generate_leaflet_markdown_block(gpx_file, title="Park Loop", distance_km=3.5)
    assert "```leaflet" in block
    assert '"title": "Park Loop"' in block

