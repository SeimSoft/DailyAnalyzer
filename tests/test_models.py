"""Tests for GarminAnalyzer data models."""

from __future__ import annotations

from garmin_analyzer.models import (
    ActivityOverview,
    DailyHealthSummary,
    LocationInfo,
    PerformanceStats,
    PhotoInfo,
)


def test_performance_stats_calculations():
    stats = PerformanceStats(
        distance_meters=10000.0,
        duration_seconds=3000.0,  # 50 minutes (5:00 /km, 12.0 km/h)
        avg_speed_mps=3.333333,
        max_speed_mps=4.5,
        average_hr=155,
        max_hr=175,
        calories=650,
        elevation_gain_meters=120.0,
    )

    assert stats.distance_km == 10.0
    assert stats.distance_miles == 6.21
    assert stats.avg_speed_kmh == 12.0
    assert stats.max_speed_kmh == 16.2
    assert stats.avg_pace_min_per_km == "05:00 /km"
    assert stats.duration_formatted == "50:00"


def test_performance_stats_duration_hours():
    stats = PerformanceStats(
        distance_meters=42195.0,
        duration_seconds=12645.0,  # 3h 30m 45s
    )
    assert stats.duration_formatted == "03:30:45"
    assert stats.distance_km == 42.2


def test_location_info():
    loc_with_coords = LocationInfo(
        start_latitude=52.5200,
        start_longitude=13.4050,
        location_name="Berlin, Germany",
    )
    assert loc_with_coords.has_coordinates is True

    loc_without_coords = LocationInfo()
    assert loc_without_coords.has_coordinates is False


def test_activity_overview_date_str():
    overview = ActivityOverview(
        activity_id=123456789,
        activity_name="Morning Run in Tiergarten",
        activity_type="running",
        start_time_local="2026-05-15 07:30:00",
        stats=PerformanceStats(distance_meters=5000.0, duration_seconds=1500.0),
    )
    assert overview.date_str == "2026-05-15"
    assert overview.activity_name == "Morning Run in Tiergarten"


def test_daily_health_summary():
    daily = DailyHealthSummary(
        date="2026-05-15",
        resting_hr=48,
        rhr_7day_avg=49.2,
        hrv_last_night_avg=65.0,
        hrv_7day_avg=62.5,
        hrv_status="BALANCED",
        hrv_baseline_low=55.0,
        hrv_baseline_high=70.0,
        steps=12540,
        steps_7day_avg=11800.0,
        sleep_seconds=28800,  # 8 hours
        sleep_score=88,
        stress_avg=24,
        body_battery_charged=65,
        body_battery_drained=60,
    )
    assert daily.sleep_duration_formatted == "8h 0m"
    assert daily.hrv_status == "BALANCED"
    assert daily.rhr_7day_avg == 49.2


def test_photo_info():
    photo = PhotoInfo(
        photo_id="photo_999",
        url="https://connect.garmin.com/media/photo_999.jpg",
        title="Summit View",
    )
    assert photo.photo_id == "photo_999"
    assert photo.title == "Summit View"
    assert photo.local_path is None
