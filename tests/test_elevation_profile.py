"""Tests for elevation profile extraction, visualization, and Plotly block generation."""

from __future__ import annotations

import json
from pathlib import Path

from garmin_analyzer.elevation_profile import (
    extract_elevation_points,
    generate_elevation_markdown_block,
    generate_elevation_plotly_spec,
    render_elevation_profile,
)
from garmin_analyzer.storyteller import assemble_self_contained_diary


def test_extract_elevation_from_raw_details(tmp_path: Path):
    act_dir = tmp_path / "activity_1"
    act_dir.mkdir()

    raw_details = {
        "metricDescriptors": [
            {"key": "sumDistance", "metricsIndex": 0},
            {"key": "directElevation", "metricsIndex": 1},
        ],
        "activityDetailMetrics": [
            {"metrics": [0.0, 800.0]},
            {"metrics": [1000.0, 950.0]},
            {"metrics": [2500.0, 1200.0]},
            {"metrics": [3000.0, 1150.0]},
        ],
    }
    (act_dir / "raw_details.json").write_text(json.dumps(raw_details), encoding="utf-8")

    points, stats = extract_elevation_points(act_dir)

    assert len(points) == 4
    assert points[0] == (0.0, 800.0)
    assert points[1] == (1.0, 950.0)
    assert points[2] == (2.5, 1200.0)
    assert points[3] == (3.0, 1150.0)

    assert stats["min_elevation"] == 800.0
    assert stats["max_elevation"] == 1200.0
    assert stats["start_elevation"] == 800.0
    assert stats["end_elevation"] == 1150.0
    assert stats["total_distance_km"] == 3.0
    assert stats["elevation_gain"] == 400.0
    assert stats["elevation_loss"] == 50.0


def test_extract_elevation_from_gpx_fallback(tmp_path: Path):
    act_dir = tmp_path / "activity_2"
    act_dir.mkdir()

    gpx_content = """<?xml version="1.0" encoding="UTF-8"?>
    <gpx version="1.1" creator="Garmin"><trk><trkseg>
        <trkpt lat="47.660" lon="11.880"><ele>950.0</ele></trkpt>
        <trkpt lat="47.665" lon="11.885"><ele>1050.0</ele></trkpt>
        <trkpt lat="47.670" lon="11.890"><ele>1140.0</ele></trkpt>
    </trkseg></trk></gpx>"""
    (act_dir / "track.gpx").write_text(gpx_content, encoding="utf-8")

    points, stats = extract_elevation_points(act_dir)

    assert len(points) == 3
    assert points[0][0] == 0.0
    assert points[0][1] == 950.0
    assert points[-1][1] == 1140.0
    assert stats["min_elevation"] == 950.0
    assert stats["max_elevation"] == 1140.0
    assert stats["elevation_gain"] == 190.0


def test_extract_elevation_empty_directory(tmp_path: Path):
    act_dir = tmp_path / "empty_activity"
    act_dir.mkdir()

    points, stats = extract_elevation_points(act_dir)
    assert points == []
    assert stats["min_elevation"] is None


def test_render_elevation_profile_png(tmp_path: Path):
    act_dir = tmp_path / "activity_render"
    act_dir.mkdir()

    raw_details = {
        "metricDescriptors": [
            {"key": "sumDistance", "metricsIndex": 0},
            {"key": "directElevation", "metricsIndex": 1},
        ],
        "activityDetailMetrics": [
            {"metrics": [0.0, 900.0]},
            {"metrics": [500.0, 1000.0]},
            {"metrics": [1200.0, 1150.0]},
            {"metrics": [2000.0, 1050.0]},
        ],
    }
    (act_dir / "raw_details.json").write_text(json.dumps(raw_details), encoding="utf-8")

    out_file = act_dir / "elevation_profile.png"
    result = render_elevation_profile(act_dir, out_file, title="Wanderung Höhenprofil")

    assert result is not None
    assert result.exists()
    assert result.stat().st_size > 1000  # Valid PNG file


def test_generate_elevation_plotly_spec(tmp_path: Path):
    act_dir = tmp_path / "activity_plotly"
    act_dir.mkdir()

    raw_details = {
        "metricDescriptors": [
            {"key": "sumDistance", "metricsIndex": 0},
            {"key": "directElevation", "metricsIndex": 1},
        ],
        "activityDetailMetrics": [
            {"metrics": [0.0, 1000.0]},
            {"metrics": [1000.0, 1200.0]},
            {"metrics": [2000.0, 1400.0]},
        ],
    }
    (act_dir / "raw_details.json").write_text(json.dumps(raw_details), encoding="utf-8")

    spec = generate_elevation_plotly_spec(act_dir, title="Gipfelwanderung")
    assert spec is not None
    assert "data" in spec
    assert "layout" in spec

    scatter = spec["data"][0]
    assert scatter["type"] == "scatter"
    assert scatter["x"] == [0.0, 1.0, 2.0]
    assert scatter["y"] == [1000.0, 1200.0, 1400.0]
    assert scatter["fill"] == "tozeroy"
    assert scatter["line"]["color"] == "#38bdf8"

    # Test markdown block
    block = generate_elevation_markdown_block(act_dir, title="Gipfelwanderung")
    assert block.startswith("```plotly\n")
    assert block.endswith("```\n")
    assert "Gipfelwanderung" in block


def test_storyteller_embeds_elevation_profile(tmp_path: Path):
    daily_dir = tmp_path / "daily_health" / "2024-08-24"
    daily_dir.mkdir(parents=True)
    (daily_dir / "raw_daily.json").write_text("{}", encoding="utf-8")

    act_dir = tmp_path / "activities" / "2024-08-24_wandern"
    act_dir.mkdir(parents=True)

    raw_details = {
        "metricDescriptors": [
            {"key": "sumDistance", "metricsIndex": 0},
            {"key": "directElevation", "metricsIndex": 1},
        ],
        "activityDetailMetrics": [
            {"metrics": [0.0, 1062.0]},
            {"metrics": [5000.0, 1142.0]},
            {"metrics": [12000.0, 956.0]},
        ],
    }
    (act_dir / "raw_details.json").write_text(json.dumps(raw_details), encoding="utf-8")

    diary_md = assemble_self_contained_diary(
        date_str="2024-08-24",
        narrative_text="Ein wunderschöner Wandertag.",
        daily_dir=daily_dir,
        activity_dirs=[act_dir],
    )

    assert "## ⛰️ Höhenprofil:" in diary_md
    assert "```plotly" in diary_md
    assert "data:image/png;base64," in diary_md
