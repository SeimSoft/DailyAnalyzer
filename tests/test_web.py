"""Tests for Garmin Analyzer FastAPI web application."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from garmin_analyzer.web.app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_index_page(client: TestClient):
    res = client.get("/")
    assert res.status_code == 200
    assert "Garmin Analyzer" in res.text


def test_auth_flow(client: TestClient):
    # 1. Initially unauthenticated
    res = client.get("/api/auth/status")
    assert res.status_code == 200
    assert res.json()["authenticated"] is False

    # 2. Login with wrong password
    res = client.post("/api/auth/login", json={"password": "wrongpassword"})
    assert res.status_code == 401

    # 3. Login with correct default password
    res = client.post("/api/auth/login", json={"password": "admin123"})
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "token" in data

    # 4. Status is now authenticated
    res = client.get("/api/auth/status")
    assert res.status_code == 200
    assert res.json()["authenticated"] is True

    # 5. Logout
    res = client.post("/api/auth/logout")
    assert res.status_code == 200

    # 6. Status is back to unauthenticated
    res = client.get("/api/auth/status")
    assert res.status_code == 200
    assert res.json()["authenticated"] is False


@patch("garmin_analyzer.web.app.get_authenticated_client")
def test_activities_endpoint(mock_get_client, client: TestClient):
    # Unauthenticated should fail
    res = client.get("/api/activities")
    assert res.status_code == 401

    # Login
    client.post("/api/auth/login", json={"password": "admin123"})

    mock_garmin = MagicMock()
    mock_garmin.get_activities.return_value = [
        {
            "activityId": 1001,
            "activityName": "Mountain Hike",
            "activityType": {"typeKey": "hiking"},
            "startTimeLocal": "2026-08-24 10:00:00",
            "distance": 5000.0,
            "duration": 3600.0,
        },
        {
            "activityId": 1002,
            "activityName": "Indoor Bike",
            "activityType": {"typeKey": "indoor_cycling"},
            "startTimeLocal": "2026-08-25 18:00:00",
            "distance": 0.0,
            "duration": 1800.0,
        },
    ]
    mock_garmin.get_activity.side_effect = lambda act_id: {
        "activityId": act_id,
        "metadataDTO": {
            "activityImages": [{"imageId": "img1", "url": "https://example.com/1.jpg"}]
            if act_id == 1001
            else []
        },
    }
    mock_get_client.return_value = mock_garmin

    with patch("garmin_analyzer.web.app.MemReportClient.get_uploaded_dates", return_value={"2026-08-24"}):
        res = client.get("/api/activities?refresh=true")
        assert res.status_code == 200
        data = res.json()
        assert "activities" in data
        assert len(data["activities"]) == 1
        assert data["activities"][0]["activity_id"] == 1001
        assert data["activities"][0]["photos_count"] == 1
        assert data["activities"][0]["memreport_uploaded"] is True
        assert "/viewer?date=2026-08-24" in data["activities"][0]["viewer_url"]



@patch("garmin_analyzer.web.app._run_report_job")
def test_generate_job_endpoint(mock_run_job, client: TestClient):
    # Login
    client.post("/api/auth/login", json={"password": "admin123"})

    res = client.post(
        "/api/generate",
        json={
            "dates": ["2026-08-24"],
            "activity_ids": [1001],
            "llm_summary": True,
            "upload": True,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert "job_id" in data

    job_id = data["job_id"]
    res_status = client.get(f"/api/jobs/{job_id}")
    assert res_status.status_code == 200
    assert res_status.json()["job_id"] == job_id
