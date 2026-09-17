"""Tests for activity and daily health markdown formatters."""

from __future__ import annotations

from garmin_analyzer.formatter import (
    format_activity_markdown,
    format_daily_markdown,
    print_activities_table,
)
from rich.console import Console
from garmin_analyzer.models import (
    ActivityOverview,
    DailyHealthSummary,
    DownloadedActivity,
    LocationInfo,
    PerformanceStats,
    PhotoInfo,
    SplitInfo,
    WeatherInfo,
)


def test_format_activity_markdown():
    overview = ActivityOverview(
        activity_id=987654321,
        activity_name="Trail Run Lake Trail",
        activity_type="running",
        activity_sub_sport="trail",
        description="Nice crisp morning run around the lake",
        start_time_local="2026-06-10 06:45:00",
        location=LocationInfo(
            start_latitude=47.3769,
            start_longitude=8.5417,
            location_name="Zurich, Switzerland",
            min_elevation_meters=410.0,
            max_elevation_meters=580.0,
        ),
        stats=PerformanceStats(
            distance_meters=12400.0,
            duration_seconds=3900.0,
            avg_speed_mps=3.179,
            average_hr=152,
            max_hr=171,
            calories=820,
            elevation_gain_meters=210.0,
            elevation_loss_meters=205.0,
            vo2_max=54.0,
        ),
        splits=[
            SplitInfo(
                split_index=1,
                distance_meters=5000.0,
                duration_seconds=1560.0,
                avg_speed_mps=3.2,
                avg_hr=148,
                elevation_gain_meters=70.0,
            ),
            SplitInfo(
                split_index=2,
                distance_meters=7400.0,
                duration_seconds=2340.0,
                avg_speed_mps=3.16,
                avg_hr=155,
                elevation_gain_meters=140.0,
            ),
        ],
        weather=WeatherInfo(
            temperature_c=14.5,
            weather_condition="Partly Cloudy",
            relative_humidity=65.0,
            wind_speed_mps=2.5,
            wind_direction_compass="NE",
        ),
    )

    daily = DailyHealthSummary(
        date="2026-06-10",
        resting_hr=49,
        rhr_7day_avg=50.1,
        hrv_last_night_avg=72.0,
        hrv_7day_avg=69.0,
        hrv_status="BALANCED",
        steps=15400,
        steps_7day_avg=12300.0,
        sleep_seconds=27600,
        sleep_score=86,
    )

    activity = DownloadedActivity(
        overview=overview,
        directory="/path/to/activity",
        track_gpx_path="/path/to/activity/track.gpx",
        track_fit_path="/path/to/activity/track.fit",
        photos=[
            PhotoInfo(
                photo_id="lake_view",
                url="https://garmin.cdn.com/lake.jpg",
                title="Lake Sunrise",
                local_path="/path/to/activity/photos/photo_01_lake_view.jpg",
            )
        ],
        daily_health=daily,
    )

    md = format_activity_markdown(activity)

    # Check key sections
    assert "# Trail Run Lake Trail" in md
    assert "## 🏃 What Have I Done" in md
    assert "Trail" in md
    assert "Nice crisp morning run around the lake" in md
    assert "## 📍 Where Was I" in md
    assert "47.3769" in md
    assert "Zurich, Switzerland" in md
    assert "`track.gpx`" in md
    assert "## 📊 All Performance Statistics" in md
    assert "12.4 km" in md
    assert "152 bpm" in md
    assert "## 🌤️ Weather Conditions" in md
    assert "14.5°C" in md
    assert "Partly Cloudy" in md
    assert "## ⏱️ Splits & Laps" in md
    assert "## 💓 Daily Health Context for 2026-06-10" in md
    assert "49 bpm" in md
    assert "50.1 bpm" in md
    assert "## 📸 Uploaded Photos & Images" in md
    assert "Lake Sunrise" in md


def test_format_daily_markdown():
    daily = DailyHealthSummary(
        date="2026-06-10",
        resting_hr=49,
        rhr_7day_avg=50.1,
        min_hr=45,
        max_hr=171,
        hrv_last_night_avg=72.0,
        hrv_7day_avg=69.0,
        hrv_status="BALANCED",
        hrv_baseline_low=60.0,
        hrv_baseline_high=78.0,
        steps=15400,
        steps_goal=10000,
        steps_7day_avg=12300.0,
        sleep_seconds=28800,
        sleep_score=90,
        sleep_deep_seconds=5400,
        sleep_light_seconds=18000,
        sleep_rem_seconds=5400,
        stress_avg=21,
        body_battery_charged=70,
        body_battery_drained=65,
        body_battery_most_recent=55,
        training_readiness_score=82,
        training_status="Maintaining",
    )

    md = format_daily_markdown(daily)
    assert "# Daily Health & 7-Day Stats: 2026-06-10" in md
    assert "50.1 bpm" in md
    assert "BALANCED" in md
    assert "12,300 steps/day" in md
    assert "8h 0m" in md
    assert "90 / 100" in md
    assert "Maintaining" in md


def test_print_activities_table_with_photos():
    console = Console(record=True, width=120)
    act1 = ActivityOverview(
        activity_id=12345,
        activity_name="Mountain Hike",
        activity_type="hiking",
        start_time_local="2026-08-24 09:30:00",
        stats=PerformanceStats(distance_meters=8500.0, duration_seconds=7200.0, average_hr=135),
        photos_count=3,
    )
    act2 = ActivityOverview(
        activity_id=67890,
        activity_name="Evening Jog",
        activity_type="running",
        start_time_local="2026-08-25 18:00:00",
        stats=PerformanceStats(distance_meters=5000.0, duration_seconds=1800.0, average_hr=150),
        photos_count=0,
    )

    print_activities_table([act1, act2], console, show_photos=True)
    output = console.export_text()

    assert "Mountain Hike" in output
    assert "Photos" in output
    assert "📸 3" in output
    assert "2026-08-24" in output

