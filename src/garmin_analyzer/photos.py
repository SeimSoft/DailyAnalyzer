"""Garmin activity photo discovery and downloader."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import requests
from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
)

from garmin_analyzer.models import PhotoInfo

logger = logging.getLogger(__name__)


def extract_photos_from_activity_dict(activity_data: dict[str, Any]) -> list[PhotoInfo]:
    """Inspects activity metadata dictionaries for photo attachments and URLs."""
    photos: list[PhotoInfo] = []
    seen_ids: set[str] = set()

    def add_photo(photo_id: str, url: str, title: str | None = None, date_taken: str | None = None):
        if not url or photo_id in seen_ids:
            return
        seen_ids.add(photo_id)
        photos.append(
            PhotoInfo(
                photo_id=str(photo_id),
                url=url,
                title=title,
                date_taken=date_taken,
                source="metadata",
            )
        )

    # 1. Inspect metadataDTO.photos & metadataDTO.activityImages
    metadata_dto = activity_data.get("metadataDTO") or {}
    if isinstance(metadata_dto, dict):
        raw_photos = metadata_dto.get("photos") or metadata_dto.get("activityImages") or []
        if isinstance(raw_photos, list):
            for idx, p in enumerate(raw_photos):
                if isinstance(p, dict):
                    pid = str(
                        p.get("imageId")
                        or p.get("photoId")
                        or p.get("id")
                        or p.get("mediaId")
                        or f"meta_{idx}"
                    )
                    url = (
                        p.get("url")
                        or p.get("fullUrl")
                        or p.get("photoUrl")
                        or p.get("imageUrl")
                        or p.get("largeUrl")
                        or p.get("mediumUrl")
                    )
                    title = p.get("title") or p.get("caption") or p.get("name")
                    date = p.get("dateTaken") or p.get("photoDate") or p.get("createdDate")
                    if url:
                        add_photo(pid, url, title, date)

    # 2. Inspect root level keys: photos, activityImages, media
    for key in ("photos", "activityImages", "media", "attachments"):
        items = activity_data.get(key)
        if isinstance(items, list):
            for idx, item in enumerate(items):
                if isinstance(item, dict):
                    pid = str(
                        item.get("photoId")
                        or item.get("id")
                        or item.get("mediaId")
                        or f"{key}_{idx}"
                    )
                    url = (
                        item.get("url")
                        or item.get("fullUrl")
                        or item.get("photoUrl")
                        or item.get("imageUrl")
                        or item.get("largeUrl")
                    )
                    if url:
                        add_photo(
                            pid,
                            url,
                            item.get("title") or item.get("caption"),
                            item.get("dateTaken"),
                        )

    return photos


def fetch_activity_photos_from_api(
    client: Garmin,
    activity_id: int | str,
    candidate_endpoints: list[str] | None = None,
) -> list[PhotoInfo]:
    """Queries Garmin Connect internal media endpoints for photos attached to the activity.

    Note: In Garmin Connect, activity photos are embedded directly in client.get_activity(id)
    under metadataDTO.activityImages (handled by extract_photos_from_activity_dict).
    Standalone /photos endpoints do not exist in Garmin Connect and trigger 404 logger exceptions.
    """
    if candidate_endpoints is None:
        return []

    photos: list[PhotoInfo] = []
    seen_ids: set[str] = set()

    for endpoint in candidate_endpoints:
        try:
            response = client.connectapi(endpoint)
            if isinstance(response, list):
                items = response
            elif isinstance(response, dict):
                items = (
                    response.get("photos")
                    or response.get("activityImages")
                    or response.get("media")
                    or [response]
                )
            else:
                items = []

            for idx, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                pid = str(
                    item.get("photoId") or item.get("id") or item.get("mediaId") or f"api_{idx}"
                )
                url = (
                    item.get("url")
                    or item.get("fullUrl")
                    or item.get("photoUrl")
                    or item.get("imageUrl")
                    or item.get("largeUrl")
                    or item.get("mediumUrl")
                )
                if url and pid not in seen_ids:
                    seen_ids.add(pid)
                    photos.append(
                        PhotoInfo(
                            photo_id=pid,
                            url=url,
                            title=item.get("title") or item.get("caption") or item.get("name"),
                            date_taken=item.get("dateTaken") or item.get("createdDate"),
                            source=endpoint,
                        )
                    )
        except (
            GarminConnectConnectionError,
            GarminConnectAuthenticationError,
            OSError,
            ValueError,
            KeyError,
        ) as e:
            logger.debug("Endpoint %s not available or returned error: %s", endpoint, e)

    return photos


def download_photo(
    client: Garmin,
    photo: PhotoInfo,
    output_dir: Path,
    index: int = 1,
) -> Path | None:
    """Downloads a photo to output_dir with proper extension and returns the local Path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    url = photo.url
    if url.startswith("/"):
        url = f"https://connect.garmin.com{url}"

    # Determine extension
    ext = ".jpg"
    if ".png" in url.lower():
        ext = ".png"
    elif ".webp" in url.lower():
        ext = ".webp"

    filename = f"photo_{index:02d}_{photo.photo_id}{ext}"
    dest_path = output_dir / filename

    if dest_path.exists() and dest_path.stat().st_size > 0:
        photo.local_path = str(dest_path)
        photo.size_bytes = dest_path.stat().st_size
        return dest_path

    try:
        raw_bytes = None
        # 1. For direct external URLs (e.g. AWS S3 presigned URLs), use standard requests directly
        if url.startswith("http://") or url.startswith("https://"):
            try:
                resp = requests.get(url, timeout=30)
                if resp.status_code == 200:
                    raw_bytes = resp.content
            except requests.RequestException as e:
                logger.debug("Direct requests download failed for %s: %s", url, e)

        # 2. Try authenticated garth client session
        if raw_bytes is None:
            session = getattr(client.client, "session", None)
            if session is not None and isinstance(session, requests.Session):
                try:
                    resp = session.get(url, timeout=30)
                    if resp.status_code == 200:
                        raw_bytes = resp.content
                except requests.RequestException:
                    pass

        # 3. Fallback to client.download
        if raw_bytes is None:
            try:
                raw_bytes = client.download(url)
            except (GarminConnectConnectionError, requests.RequestException, OSError):
                pass

        if raw_bytes:
            dest_path.write_bytes(raw_bytes)
            photo.local_path = str(dest_path)
            photo.size_bytes = len(raw_bytes)
            return dest_path

    except (GarminConnectConnectionError, requests.RequestException, OSError) as err:
        logger.warning("Failed to download photo %s from %s: %s", photo.photo_id, url, err)

    return None
