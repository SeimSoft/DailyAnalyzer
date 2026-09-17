"""Tests for health evaluator logic and judgments."""

from __future__ import annotations

from pathlib import Path

from garmin_analyzer.evaluator import (
    evaluate_daily_health,
    save_evaluations,
)
from garmin_analyzer.models import DailyHealthSummary


def test_evaluate_daily_health_normal():
    daily = DailyHealthSummary(
        date="2026-06-15",
        resting_hr=52,
        rhr_7day_avg=52.0,
        hrv_last_night_avg=68.0,
        hrv_7day_avg=66.0,
        hrv_status="BALANCED",
        hrv_baseline_low=60.0,
        hrv_baseline_high=75.0,
        steps=10500,
        steps_goal=10000,
        steps_7day_avg=9800.0,
        sleep_seconds=28800,  # 8h
        sleep_score=85,
        stress_avg=24,
        body_battery_charged=70,
        body_battery_drained=65,
        body_battery_most_recent=45,
    )

    ev = evaluate_daily_health(daily)
    assert ev.date == "2026-06-15"
    assert ev.heart_rate.status == "Normal"
    assert ev.heart_rate.is_positive is True
    assert ev.hrv.status == "Normal"
    assert ev.hrv.is_positive is True
    assert ev.stress.status == "Very Low / Restful"
    assert ev.sleep.status == "Slept Well"
    assert ev.body_battery.status == "Positive Energy Balance"
    assert ev.activity.status == "Goal Achieved"
    assert "Optimal Recovery" in ev.overall_verdict


def test_evaluate_daily_health_elevated_strain():
    daily = DailyHealthSummary(
        date="2026-06-16",
        resting_hr=58,  # +6 bpm above 7d avg
        rhr_7day_avg=52.0,
        hrv_last_night_avg=45.0,  # below baseline
        hrv_7day_avg=65.0,
        hrv_status="LOW",
        hrv_baseline_low=58.0,
        hrv_baseline_high=75.0,
        steps=3200,
        steps_goal=10000,
        sleep_seconds=18000,  # 5 hours
        sleep_score=55,
        stress_avg=58,  # High stress
        body_battery_charged=30,
        body_battery_drained=75,
    )

    ev = evaluate_daily_health(daily)
    assert ev.heart_rate.status == "Higher than usual"
    assert ev.heart_rate.is_positive is False
    assert ev.hrv.status == "Low / Subnormal"
    assert ev.hrv.is_positive is False
    assert ev.stress.status == "High Stress"
    assert ev.sleep.status == "Poor Sleep"
    assert ev.body_battery.status == "Heavy Drain"
    assert "Recovery Strain" in ev.overall_verdict


def test_save_evaluations(tmp_path: Path):
    daily = DailyHealthSummary(
        date="2026-06-17",
        resting_hr=50,
        stress_avg=20,
        sleep_score=90,
    )
    ev = evaluate_daily_health(daily)
    md_file, json_file = save_evaluations(ev, tmp_path)

    assert md_file.exists()
    assert json_file.exists()
    assert "Health Evaluation: 2026-06-17" in md_file.read_text(encoding="utf-8")
    assert "Resting Heart Rate" in md_file.read_text(encoding="utf-8")
