"""Tests for high-level GarminAnalyzer client and batch downloads."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

from garmin_analyzer.client import GarminAnalyzer


def test_download_activity_and_files(tmp_path: Path):
    mock_client = MagicMock()
    mock_client.ActivityDownloadFormat = MagicMock()
    mock_client.ActivityDownloadFormat.GPX = "gpx"
    mock_client.ActivityDownloadFormat.TCX = "tcx"
    mock_client.ActivityDownloadFormat.ORIGINAL = "original"

    # Mock track downloads
    mock_client.download_activity.side_effect = lambda act_id, dl_fmt: (
        b"<gpx>mock</gpx>"
        if dl_fmt == "gpx"
        else b"<tcx>mock</tcx>"
        if dl_fmt == "tcx"
        else _create_mock_fit_zip()
    )

    # Mock details & splits & weather
    mock_client.get_activity_details.return_value = {"activityDetails": "mock"}
    mock_client.get_activity_splits.return_value = {
        "lapDTOs": [
            {
                "distance": 1000.0,
                "duration": 300.0,
                "averageSpeed": 3.33,
                "averageHR": 145,
            }
        ]
    }
    mock_client.get_activity_weather.return_value = {
        "temp": 18.0,
        "weatherCondition": "Sunny",
    }
    mock_client.get_activity_hr_in_timezones.return_value = {"zone1": 120}

    # Mock daily health queries
    mock_client.get_user_summary.return_value = {
        "totalSteps": 10500,
        "restingHeartRate": 52,
    }
    mock_client.get_heart_rates.return_value = {"restingHeartRate": 52}
    mock_client.get_rhr_day.return_value = {"wellnessSevenDayAvgRestingHeartRate": 51.5}
    mock_client.get_hrv_data.return_value = {
        "hrvSummary": {"weeklyAvg": 65.0, "lastNightAvg": 66.0, "status": "BALANCED"}
    }
    mock_client.get_daily_steps.return_value = [{"calendarDate": "2026-06-15", "totalSteps": 10500}]
    mock_client.get_sleep_data.return_value = {
        "dailySleepDTO": {"sleepTimeSeconds": 27000, "sleepScores": {"overall": {"value": 80}}}
    }
    mock_client.get_stress_data.return_value = {"avgStressLevel": 25}
    mock_client.get_body_battery.return_value = []
    mock_client.get_training_readiness.return_value = None
    mock_client.get_training_status.return_value = None

    # Mock photo download
    mock_client.download.return_value = b"\xff\xd8\xfffake_photo"
    mock_client.client.session = None
    mock_client.connectapi.return_value = []

    analyzer = GarminAnalyzer(mock_client)

    raw_activity = {
        "activityId": 11223344,
        "activityName": "Forest Trail Run",
        "activityType": {"typeKey": "running"},
        "startTimeLocal": "2026-06-15 09:00:00",
        "distance": 10000.0,
        "duration": 3000.0,
        "averageHR": 150,
        "maxHR": 170,
        "startLatitude": 52.5,
        "startLongitude": 13.4,
        "metadataDTO": {
            "photos": [
                {
                    "photoId": "trail_01",
                    "url": "https://garmin.cdn.com/trail1.jpg",
                    "title": "Trail Photo",
                }
            ]
        },
    }

    downloaded = analyzer.download_activity(
        raw_activity,
        output_dir=tmp_path,
        include_tracks=True,
        include_photos=True,
        include_daily=True,
    )

    act_dir = Path(downloaded.directory)
    assert act_dir.exists()

    # Verify files created
    assert (act_dir / "raw_activity.json").exists()
    assert (act_dir / "raw_details.json").exists()
    assert (act_dir / "splits.json").exists()
    assert (act_dir / "weather.json").exists()
    assert (act_dir / "hr_zones.json").exists()
    assert (act_dir / "track.gpx").exists()
    assert (act_dir / "track.tcx").exists()
    assert (act_dir / "track.fit").exists()
    assert (act_dir / "track.fit").read_bytes() == b"fake_fit_binary_data"
    assert (act_dir / "activity_summary.json").exists()
    assert (act_dir / "activity_summary.md").exists()

    # Photos
    photos_dir = act_dir / "photos"
    assert photos_dir.exists()
    assert len(list(photos_dir.glob("*.jpg"))) == 1

    # Daily health
    daily_dir = tmp_path / "daily_health" / "2026-06-15"
    assert daily_dir.exists()
    assert (daily_dir / "daily_summary.json").exists()
    assert (daily_dir / "daily_summary.md").exists()


def test_download_batch_and_indexes(tmp_path: Path):
    mock_client = MagicMock()
    mock_client.get_activities.return_value = [
        {
            "activityId": 101,
            "activityName": "Morning Jog",
            "activityType": {"typeKey": "running"},
            "startTimeLocal": "2026-06-16 08:00:00",
            "distance": 5000.0,
            "duration": 1500.0,
            "averageHR": 140,
        },
        {
            "activityId": 102,
            "activityName": "Evening Walk",
            "activityType": {"typeKey": "walking"},
            "startTimeLocal": "2026-06-16 19:00:00",
            "distance": 3000.0,
            "duration": 2100.0,
        },
    ]
    mock_client.get_activity_details.return_value = {}
    mock_client.get_activity_splits.return_value = {}
    mock_client.get_activity_weather.return_value = {}
    mock_client.get_activity_hr_in_timezones.return_value = {}
    mock_client.get_user_summary.return_value = {"totalSteps": 8000}
    mock_client.get_heart_rates.return_value = {}
    mock_client.get_rhr_day.return_value = {}
    mock_client.get_hrv_data.return_value = {}
    mock_client.get_daily_steps.return_value = []
    mock_client.get_sleep_data.return_value = {}
    mock_client.get_stress_data.return_value = {}
    mock_client.get_body_battery.return_value = []
    mock_client.get_training_readiness.return_value = None
    mock_client.get_training_status.return_value = None
    mock_client.connectapi.return_value = []

    analyzer = GarminAnalyzer(mock_client)
    results = analyzer.download_batch(
        limit=2,
        output_dir=tmp_path,
        include_tracks=False,
        include_photos=False,
        include_daily=True,
    )

    assert len(results) == 2

    # Indexes
    json_index = tmp_path / "activities_index.json"
    csv_index = tmp_path / "activities_index.csv"
    assert json_index.exists()
    assert csv_index.exists()

    index_data = json.loads(json_index.read_text())
    assert len(index_data) == 2
    assert index_data[0]["activity_id"] == 101
    assert index_data[1]["activity_id"] == 102


def test_download_daily_with_activities(tmp_path: Path):
    mock_client = MagicMock()
    mock_client.get_activities_by_date.return_value = [
        {
            "activityId": 201,
            "activityName": "Afternoon Walk",
            "activityType": {"typeKey": "walking"},
            "startTimeLocal": "2026-06-16 15:30:00",
            "distance": 4200.0,
            "duration": 2500.0,
            "averageHR": 95,
        }
    ]
    mock_client.get_activity_details.return_value = {}
    mock_client.get_activity_splits.return_value = {}
    mock_client.get_activity_weather.return_value = {}
    mock_client.get_activity_hr_in_timezones.return_value = {}
    mock_client.get_user_summary.return_value = {"totalSteps": 9500, "restingHeartRate": 55}
    mock_client.get_heart_rates.return_value = {"restingHeartRate": 55}
    mock_client.get_rhr_day.return_value = {"wellnessSevenDayAvgRestingHeartRate": 54.0}
    mock_client.get_hrv_data.return_value = {}
    mock_client.get_daily_steps.return_value = []
    mock_client.get_sleep_data.return_value = {}
    mock_client.get_stress_data.return_value = {}
    mock_client.get_body_battery.return_value = []
    mock_client.get_training_readiness.return_value = None
    mock_client.get_training_status.return_value = None
    mock_client.connectapi.return_value = []

    analyzer = GarminAnalyzer(mock_client)
    summary, downloaded_acts, _ = analyzer.download_daily(
        "2026-06-16",
        output_dir=tmp_path,
        include_activities=True,
        include_tracks=False,
        include_photos=False,
    )

    assert len(downloaded_acts) == 1
    assert downloaded_acts[0].overview.activity_id == 201
    assert len(summary.activities) == 1
    assert summary.activities[0].activity_name == "Afternoon Walk"

    # Verify activity files were saved
    act_path = Path(downloaded_acts[0].directory)
    assert act_path.exists()
    assert (act_path / "activity_summary.json").exists()
    assert (act_path / "activity_summary.md").exists()

    # Verify daily summary markdown mentions the activity
    daily_md = tmp_path / "daily_health" / "2026-06-16" / "daily_summary.md"
    assert daily_md.exists()
    md_content = daily_md.read_text()
    assert "Afternoon Walk" in md_content
    assert "Activities on This Day" in md_content


def _create_mock_fit_zip() -> bytes:
    """Helper to create a zip containing a mock .fit file."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("activity_11223344.fit", b"fake_fit_binary_data")
    return buf.getvalue()


def test_check_activities_photos():
    mock_client = MagicMock()
    mock_client.get_activity.side_effect = lambda act_id: {
        "activityId": act_id,
        "metadataDTO": {
            "activityImages": [{"imageId": f"img_{act_id}_1", "url": "https://example.com/1.jpg"}]
            if act_id == 100
            else []
        },
    }

    analyzer = GarminAnalyzer(mock_client)
    acts = [
        analyzer.parse_activity({"activityId": 100, "activityName": "Run with photo"}),
        analyzer.parse_activity({"activityId": 200, "activityName": "Run without photo"}),
    ]

    analyzer.check_activities_photos(acts)

    assert acts[0].photos_count == 1
    assert acts[1].photos_count == 0

