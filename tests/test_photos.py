"""Tests for photo extraction and download module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from garmin_analyzer.models import PhotoInfo
from garmin_analyzer.photos import (
    download_photo,
    extract_photos_from_activity_dict,
    fetch_activity_photos_from_api,
)


def test_extract_photos_from_metadata_dto():
    activity_data = {
        "activityId": 12345,
        "metadataDTO": {
            "photos": [
                {
                    "photoId": "ph_01",
                    "url": "https://garmin.cdn.com/photos/ph_01.jpg",
                    "title": "Starting Line",
                    "dateTaken": "2026-06-01T08:00:00",
                },
                {
                    "id": "ph_02",
                    "fullUrl": "https://garmin.cdn.com/photos/ph_02.png",
                    "caption": "Mountain Peak",
                },
            ]
        },
    }

    photos = extract_photos_from_activity_dict(activity_data)
    assert len(photos) == 2
    assert photos[0].photo_id == "ph_01"
    assert photos[0].title == "Starting Line"
    assert photos[1].photo_id == "ph_02"
    assert photos[1].title == "Mountain Peak"


def test_extract_photos_from_activity_images():
    activity_data = {
        "activityId": 24099165984,
        "metadataDTO": {
            "activityImages": [
                {
                    "imageId": "img_abc123",
                    "url": "https://garmin-connect-prod.s3.amazonaws.com/activity_images/abc-larg.jpg",
                    "mediumUrl": "https://garmin-connect-prod.s3.amazonaws.com/activity_images/abc-mdfd.jpg",
                    "title": "Summit View",
                }
            ]
        },
    }
    photos = extract_photos_from_activity_dict(activity_data)
    assert len(photos) == 1
    assert photos[0].photo_id == "img_abc123"
    assert photos[0].url.startswith("https://garmin-connect-prod.s3.amazonaws.com")
    assert photos[0].title == "Summit View"


def test_extract_photos_from_root_keys_and_deduplication():
    activity_data = {
        "activityId": 12345,
        "photos": [
            {
                "photoId": "ph_01",
                "url": "https://garmin.cdn.com/photos/ph_01.jpg",
            }
        ],
        "media": [
            {
                "mediaId": "ph_01",  # duplicate ID
                "url": "https://garmin.cdn.com/photos/ph_01.jpg",
            },
            {
                "mediaId": "ph_03",
                "imageUrl": "https://garmin.cdn.com/photos/ph_03.jpg",
                "title": "Medal",
            },
        ],
    }

    photos = extract_photos_from_activity_dict(activity_data)
    assert len(photos) == 2
    ids = [p.photo_id for p in photos]
    assert "ph_01" in ids
    assert "ph_03" in ids


def test_fetch_activity_photos_from_api():
    mock_client = MagicMock()
    mock_client.connectapi.side_effect = [
        [
            {
                "photoId": "api_photo_1",
                "url": "https://connect.garmin.com/api/media/1.jpg",
                "title": "Trail View",
            }
        ],
        [],  # second candidate endpoint
        [],  # third candidate endpoint
    ]

    photos = fetch_activity_photos_from_api(
        mock_client, 12345, candidate_endpoints=["/candidate/photos"]
    )
    assert len(photos) == 1
    assert photos[0].photo_id == "api_photo_1"
    assert photos[0].title == "Trail View"


def test_download_photo(tmp_path: Path):
    mock_client = MagicMock()
    fake_image_bytes = b"\xff\xd8\xff\xe0fake_jpeg_content"
    mock_client.download.return_value = fake_image_bytes
    mock_client.client.session = None

    photo = PhotoInfo(
        photo_id="test_photo_100",
        url="https://garmin.cdn.com/img100.jpg",
        title="Test Image",
    )

    dest = download_photo(mock_client, photo, tmp_path, index=1)
    assert dest is not None
    assert dest.exists()
    assert dest.read_bytes() == fake_image_bytes
    assert photo.local_path == str(dest)
    assert photo.size_bytes == len(fake_image_bytes)
