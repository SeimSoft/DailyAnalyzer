"""Tests for daily health timeseries visualizer."""

from __future__ import annotations

from pathlib import Path

from garmin_analyzer.visualizer import (
    generate_all_daily_visualizations,
    plot_body_battery_vs_time,
    plot_heart_rate_vs_time,
    plot_hrv_vs_time,
    plot_stress_vs_time,
)


def test_visualizations_generated(tmp_path: Path):
    raw_data = {
        "date": "2026-06-15",
        "heart_rates": {
            "restingHeartRate": 52,
            "maxHeartRate": 160,
            "heartRateValues": [
                [1781510000000, 55],
                [1781520000000, 65],
                [1781530000000, 75],
                [1781540000000, 60],
            ],
        },
        "stress": {
            "avgStressLevel": 28,
            "stressValuesArray": [
                [1781510000000, 15],
                [1781520000000, 35],
                [1781530000000, 55],
            ],
        },
        "body_battery": [
            {
                "charged": 60,
                "drained": 50,
                "bodyBatteryValuesArray": [
                    [1781510000000, 80],
                    [1781520000000, 70],
                    [1781530000000, 50],
                ],
            }
        ],
        "hrv": {
            "hrvSummary": {
                "status": "BALANCED",
                "lastNightAvg": 68.0,
                "weeklyAvg": 65.0,
                "baseline": {"balancedLow": 58.0, "balancedUpper": 75.0},
            },
            "hrvReadings": [
                {"hrvValue": 65, "readingTimeLocal": "2026-06-15T02:00:00.0"},
                {"hrvValue": 70, "readingTimeLocal": "2026-06-15T03:00:00.0"},
            ],
        },
    }

    files = generate_all_daily_visualizations(raw_data, tmp_path)
    assert len(files) == 4

    charts_dir = tmp_path / "charts"
    assert (charts_dir / "heart_rate_vs_time.png").exists()
    assert (charts_dir / "heart_rate_vs_time.svg").exists()
    assert (charts_dir / "stress_vs_time.png").exists()
    assert (charts_dir / "stress_vs_time.svg").exists()
    assert (charts_dir / "body_battery_vs_time.png").exists()
    assert (charts_dir / "body_battery_vs_time.svg").exists()
    assert (charts_dir / "hrv_vs_time.png").exists()
    assert (charts_dir / "hrv_vs_time.svg").exists()


def test_visualizer_empty_data_graceful(tmp_path: Path):
    raw_data = {"date": "2026-06-15"}
    assert plot_heart_rate_vs_time(raw_data, tmp_path) is None
    assert plot_stress_vs_time(raw_data, tmp_path) is None
    assert plot_body_battery_vs_time(raw_data, tmp_path) is None
    assert plot_hrv_vs_time(raw_data, tmp_path) is None


def test_interactive_plotly_specs():
    from garmin_analyzer.visualizer import (
        generate_all_interactive_plotly_blocks,
        generate_body_battery_plotly_spec,
        generate_heart_rate_plotly_spec,
        generate_hrv_plotly_spec,
        generate_stress_plotly_spec,
    )

    raw_data = {
        "date": "2026-06-15",
        "heart_rates": {
            "restingHeartRate": 52,
            "maxHeartRate": 160,
            "heartRateValues": [[1781510000000, 55], [1781520000000, 65]],
        },
        "stress": {
            "avgStressLevel": 28,
            "stressValuesArray": [[1781510000000, 15], [1781520000000, 35]],
        },
        "body_battery": [
            {
                "charged": 60,
                "drained": 50,
                "bodyBatteryValuesArray": [[1781510000000, 80], [1781520000000, 70]],
            }
        ],
        "hrv": {
            "hrvSummary": {"status": "BALANCED", "lastNightAvg": 68.0, "weeklyAvg": 65.0},
            "hrvReadings": [{"hrvValue": 65, "readingTimeLocal": "2026-06-15T02:00:00.0"}],
        },
    }

    hr_spec = generate_heart_rate_plotly_spec(raw_data)
    assert hr_spec is not None
    assert len(hr_spec["data"][0]["y"]) == 2

    stress_spec = generate_stress_plotly_spec(raw_data)
    assert stress_spec is not None
    assert stress_spec["layout"]["yaxis"]["range"] == [0, 100]

    bb_spec = generate_body_battery_plotly_spec(raw_data)
    assert bb_spec is not None
    assert bb_spec["data"][0]["name"] == "Body Battery"

    hrv_spec = generate_hrv_plotly_spec(raw_data)
    assert hrv_spec is not None
    assert hrv_spec["data"][0]["name"] == "5-min HRV"

    blocks = generate_all_interactive_plotly_blocks(raw_data)
    assert "heart_rate" in blocks
    assert "stress" in blocks
    assert "body_battery" in blocks
    assert "hrv" in blocks
    assert "```plotly" in blocks["heart_rate"]

