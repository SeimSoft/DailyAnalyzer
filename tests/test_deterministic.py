"""Unit tests for deterministic summary generation (0 token cost)."""

from __future__ import annotations

import json
from pathlib import Path

from garmin_analyzer.deterministic import (
    SPORT_CONFIG,
    _format_duration,
    _format_pace_or_speed,
    format_german_date,
    generate_deterministic_daily_story,
    generate_deterministic_narrative,
)


def test_format_helpers():
    assert format_german_date("2026-06-16") == "Dienstag, 16. Juni 2026"
    assert format_german_date("2024-08-24") == "Samstag, 24. August 2024"
    assert format_german_date("invalid-date") == "invalid-date"

    assert _format_duration(3600) == "01:00:00 h"
    assert _format_duration(5520) == "01:32:00 h"
    assert _format_duration(45) == "00:45 min"
    assert _format_duration(0) == "00:00"

    # Running pace: 10 km in 50 min (3000s) = 05:00 /km
    pace_str = _format_pace_or_speed("running", 10.0, 3000.0)
    assert pace_str == "05:00 /km"

    # Cycling speed: 30 km in 3600s = 30.0 km/h
    speed_str = _format_pace_or_speed("cycling", 30.0, 3600.0)
    assert speed_str == "30.0 km/h"


def test_generate_deterministic_narrative_hiking(tmp_path: Path):
    daily_dir = tmp_path / "daily_health" / "2026-06-16"
    daily_dir.mkdir(parents=True)

    act_dir = tmp_path / "activities" / "2026-06-16_123_hiking"
    act_dir.mkdir(parents=True)
    raw_act = {
        "activityName": "Wanderung auf den Hochfelln",
        "activityType": {"typeKey": "hiking"},
        "distance": 12500.0,
        "duration": 14400.0,
        "totalElevationGain": 850.0,
        "averageHR": 142,
        "maxHR": 171,
        "description": "Schöne Aussicht am Gipfelkreuz.",
    }
    (act_dir / "raw_activity.json").write_text(json.dumps(raw_act), encoding="utf-8")

    narrative = generate_deterministic_narrative(
        date_str="2026-06-16",
        daily_dir=daily_dir,
        activity_dirs=[act_dir],
        user_notes="Tolles Wetter, Geburtstag gefeiert!",
    )

    assert "# 🥾 Wanderung auf den Hochfelln" in narrative
    assert "Dienstag, 16. Juni 2026" in narrative
    assert "12.5 km" in narrative
    assert "+850 Höhenmetern" in narrative
    assert "Tolles Wetter, Geburtstag gefeiert!" in narrative
    assert "Schöne Aussicht am Gipfelkreuz." in narrative
    assert "| 📏 **Distanz** | 12.50 km |" in narrative
    assert "| ⛰️ **Höhenmeter** | +850 m |" in narrative


def test_generate_deterministic_narrative_running_and_cycling(tmp_path: Path):
    daily_dir = tmp_path / "daily_health" / "2026-06-16"
    daily_dir.mkdir(parents=True)

    daily_summary_text = """# Tagesübersicht: 2026-06-16
## 💤 Schlaf & Erholung
- Gesamtschlaf: 7h 45m
- Schlafqualität: Sehr gut

## ⚡ Stress & Body Battery
- Durchschnittlicher Stress: 24 (Niedrig)
- Schritte: 16.400
"""
    (daily_dir / "daily_summary.md").write_text(daily_summary_text, encoding="utf-8")

    act_run = tmp_path / "activities" / "2026-06-16_101_running"
    act_run.mkdir(parents=True)
    raw_run = {
        "activityName": "Morgenlauf",
        "activityType": {"typeKey": "running"},
        "distance": 10200.0,
        "duration": 3120.0,
        "averageHR": 155,
        "maxHR": 178,
        "elevationGain": 60.0,
    }
    (act_run / "raw_activity.json").write_text(json.dumps(raw_run), encoding="utf-8")

    act_bike = tmp_path / "activities" / "2026-06-16_102_cycling"
    act_bike.mkdir(parents=True)
    raw_bike = {
        "activityName": "Feierabendrunde",
        "activityType": {"typeKey": "cycling"},
        "distance": 35000.0,
        "duration": 4800.0,
        "averageHR": 130,
        "maxHR": 152,
        "elevationGain": 210.0,
    }
    (act_bike / "raw_activity.json").write_text(json.dumps(raw_bike), encoding="utf-8")

    narrative = generate_deterministic_narrative(
        date_str="2026-06-16",
        daily_dir=daily_dir,
        activity_dirs=[act_run, act_bike],
    )

    assert "Morgenlauf" in narrative
    assert "Schlaf & Tagesgesundheit" in narrative
    assert "Gesamtschlaf: 7h 45m" in narrative


def test_generate_deterministic_daily_story(tmp_path: Path):
    daily_dir = tmp_path / "daily_health" / "2026-06-16"
    daily_dir.mkdir(parents=True)
    charts_dir = daily_dir / "charts"
    charts_dir.mkdir(parents=True)
    (charts_dir / "heart_rate_vs_time.png").write_bytes(b"\x89PNGfakehr")

    act_dir = tmp_path / "activities" / "2026-06-16_999_hiking"
    act_dir.mkdir(parents=True)
    (act_dir / "gps_map.png").write_bytes(b"\x89PNGfakemap")
    (act_dir / "elevation_profile.png").write_bytes(b"\x89PNGfakeelevation")

    act = {
        "activityId": 999,
        "activityName": "Alpenüberquerung Etappe 1",
        "activityType": {"typeKey": "hiking"},
        "distance": 18200.0,
        "duration": 21600.0,
        "totalElevationGain": 1240.0,
    }
    (act_dir / "raw_activity.json").write_text(json.dumps(act), encoding="utf-8")

    story_path, content = generate_deterministic_daily_story(
        date_str="2026-06-16",
        daily_dir=daily_dir,
        activity_dirs=[act_dir],
        user_notes="Perfekter Bergtag",
    )

    assert story_path.exists()
    assert "# 🥾 Alpenüberquerung Etappe 1" in content
    assert "Perfekter Bergtag" in content
    assert "GPS Route:" in content
    assert "Höhenprofil" in content
    assert "data:image/png;base64," in content
