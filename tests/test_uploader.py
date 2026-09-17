"""Unit tests for MemReportClient uploader."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from garmin_analyzer.uploader import MemReportClient


def test_memreport_client_init_url_cleaning():
    client = MemReportClient(base_url="http://192.168.2.41:8125/memreport/docs/")
    assert client.base_url == "http://192.168.2.41:8125/memreport"

    client2 = MemReportClient(base_url="http://127.0.0.1:8000/viewer")
    assert client2.base_url == "http://127.0.0.1:8000"


@patch("garmin_analyzer.uploader.requests.Session.post")
def test_memreport_login_success(mock_post):
    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_res.json.return_value = {"access_token": "fake-jwt-token", "token_type": "bearer"}
    mock_post.return_value = mock_res

    client = MemReportClient(base_url="http://testserver")
    token = client.login()

    assert token == "fake-jwt-token"
    assert client.token == "fake-jwt-token"
    assert client.session.headers.get("Authorization") == "Bearer fake-jwt-token"


@patch("garmin_analyzer.uploader.requests.Session.post")
def test_memreport_login_failure(mock_post):
    mock_res = MagicMock()
    mock_res.raise_for_status.side_effect = requests.HTTPError("401 Unauthorized")
    mock_post.return_value = mock_res

    client = MemReportClient(base_url="http://testserver")
    with pytest.raises(ConnectionError):
        client.login()


@patch("garmin_analyzer.uploader.requests.Session.put")
@patch("garmin_analyzer.uploader.requests.Session.post")
def test_memreport_upload_file(mock_post, mock_put, tmp_path: Path):
    mock_post_res = MagicMock()
    mock_post_res.status_code = 200
    mock_post_res.json.side_effect = [
        {"access_token": "fake-token"},
        {"id": 1, "date": "2026-09-16", "content_type": "markdown"},
    ]
    mock_post.return_value = mock_post_res

    mock_put_res = MagicMock()
    mock_put_res.status_code = 200
    mock_put_res.json.return_value = {"status": "ok"}
    mock_put.return_value = mock_put_res

    test_md = tmp_path / "report.md"
    test_md.write_text("# Test Report", encoding="utf-8")

    client = MemReportClient(base_url="http://testserver")
    res = client.upload_file(
        file_path=test_md,
        date_str="2026-09-16",
        latitude=47.88,
        longitude=11.91,
        location_name="Bruckmühl",
    )

    assert res["date"] == "2026-09-16"
    assert mock_post.call_count >= 1
    mock_put.assert_called_once()
