"""Tests for daily health and 7-day trend statistics."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from garmin_analyzer.daily import fetch_daily_health, parse_date_input


def test_parse_date_input():
    # European / German dot-separated format
    d_str, _ = parse_date_input("16.09.2026")
    assert d_str == "2026-09-16"

    # Slashes with dayfirst
    d_str, _ = parse_date_input("16/09/2026")
    assert d_str == "2026-09-16"

    # ISO format
    d_str, _ = parse_date_input("2026-09-16")
    assert d_str == "2026-09-16"

    # Relative shortcuts
    d_today, _ = parse_date_input("today")
    assert len(d_today) == 10 and d_today.count("-") == 2

    d_none, _ = parse_date_input(None)
    assert d_none == d_today

    d_yest, _ = parse_date_input("yesterday")
    assert len(d_yest) == 10 and d_yest.count("-") == 2

    # Invalid string raises ValueError
    with pytest.raises(ValueError):
        parse_date_input("not-a-valid-date-string")


def test_fetch_daily_health_aggregation():
    mock_client = MagicMock()

    # Mock user summary
    mock_client.get_user_summary.return_value = {
        "totalSteps": 11200,
        "dailyStepGoal": 10000,
        "floorsAscended": 14,
        "restingHeartRate": 51,
        "minHeartRate": 47,
        "maxHeartRate": 168,
        "averageStressLevel": 28,
    }

    # Mock heart rates
    mock_client.get_heart_rates.return_value = {
        "restingHeartRate": 51,
        "minHeartRate": 47,
        "maxHeartRate": 168,
    }

    # Mock 7-day RHR
    mock_client.get_rhr_day.return_value = {
        "wellnessSevenDayAvgRestingHeartRate": 50.4,
    }

    # Mock HRV data
    mock_client.get_hrv_data.return_value = {
        "hrvSummary": {
            "weeklyAvg": 68.0,
            "lastNightAvg": 71.0,
            "status": "BALANCED",
            "baseline": {
                "balancedLow": 62.0,
                "balancedUpper": 78.0,
            },
        }
    }

    # Mock 7-day daily steps
    mock_client.get_daily_steps.return_value = [
        {"calendarDate": "2026-06-01", "totalSteps": 10000, "stepGoal": 10000},
        {"calendarDate": "2026-06-02", "totalSteps": 12000, "stepGoal": 10000},
        {"calendarDate": "2026-06-03", "totalSteps": 9500, "stepGoal": 10000},
        {"calendarDate": "2026-06-04", "totalSteps": 14000, "stepGoal": 10000},
        {"calendarDate": "2026-06-05", "totalSteps": 11000, "stepGoal": 10000},
        {"calendarDate": "2026-06-06", "totalSteps": 8500, "stepGoal": 10000},
        {"calendarDate": "2026-06-07", "totalSteps": 11200, "stepGoal": 10000},
    ]

    # Mock sleep data
    mock_client.get_sleep_data.return_value = {
        "dailySleepDTO": {
            "sleepTimeSeconds": 27000,  # 7h 30m
            "deepSleepSeconds": 5400,
            "lightSleepSeconds": 16200,
            "remSleepSeconds": 5400,
            "awakeSleepSeconds": 1200,
            "sleepScores": {"overall": {"value": 85}},
        }
    }

    # Mock stress data
    mock_client.get_stress_data.return_value = {"avgStressLevel": 28}

    # Mock body battery
    mock_client.get_body_battery.return_value = [
        {
            "charged": 65,
            "drained": 58,
            "bodyBatteryMostRecentValue": 42,
        }
    ]

    # Mock training readiness and status
    mock_client.get_training_readiness.return_value = {"score": 78}
    mock_client.get_training_status.return_value = {"trainingStatusFeedbackPhrase": "Productive"}

    summary, raw_data = fetch_daily_health(mock_client, "2026-06-07")

    # Verifications
    assert summary.date == "2026-06-07"
    assert summary.resting_hr == 51
    assert summary.rhr_7day_avg == 50.4
    assert summary.hrv_last_night_avg == 71.0
    assert summary.hrv_7day_avg == 68.0
    assert summary.hrv_status == "BALANCED"
    assert summary.hrv_baseline_low == 62.0
    assert summary.hrv_baseline_high == 78.0

    # Steps & 7-day average: (10000+12000+9500+14000+11000+8500+11200) / 7 = 76200 / 7 = 10885.7
    assert summary.steps == 11200
    assert summary.steps_7day_avg == 10885.7

    # Sleep
    assert summary.sleep_score == 85
    assert summary.sleep_duration_formatted == "7h 30m"

    # Stress & Body Battery
    assert summary.stress_avg == 28
    assert summary.body_battery_charged == 65
    assert summary.body_battery_drained == 58
    assert summary.body_battery_most_recent == 42

    # Training
    assert summary.training_readiness_score == 78
    assert summary.training_status == "Productive"

    # Raw payload saved
    assert "user_summary" in raw_data
    assert "steps_7d_history" in raw_data
