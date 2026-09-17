"""Client for uploading reports, interactive visuals, and GPS metadata to MemReport."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

DEFAULT_MEMREPORT_URL = os.getenv("MEMREPORT_URL", "http://192.168.2.41:8125/memreport")
DEFAULT_USERNAME = os.getenv("MEMREPORT_USER", "admin")
DEFAULT_PASSWORD = os.getenv("MEMREPORT_PASSWORD", "admin123")


class MemReportClient:
    """HTTP client for MemReport REST API."""

    def __init__(
        self,
        base_url: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        raw_url = (base_url or DEFAULT_MEMREPORT_URL).strip()
        # Clean up URL if user passed /docs, /viewer, or trailing slash
        for suffix in ("/docs", "/docs/", "/viewer", "/viewer/", "/openapi.json"):
            if raw_url.endswith(suffix):
                raw_url = raw_url[: -len(suffix)]
        self.base_url = raw_url.rstrip("/")

        self.username = username or DEFAULT_USERNAME
        self.password = password or DEFAULT_PASSWORD
        self.token: str | None = None
        self.session = requests.Session()

    def login(self) -> str:
        """Authenticates with MemReport and obtains a bearer access token."""
        url = f"{self.base_url}/api/auth/login"
        payload = {"username": self.username, "password": self.password}
        logger.debug("Authenticating with MemReport at %s as user '%s'", url, self.username)

        try:
            res = self.session.post(url, json=payload, timeout=10)
            res.raise_for_status()
            data = res.json()
            token = data.get("access_token")
            if not token:
                raise ValueError("No access_token returned by MemReport login endpoint")
            self.token = token
            self.session.headers.update({"Authorization": f"Bearer {token}"})
            logger.info("Successfully authenticated with MemReport (%s)", self.base_url)
            return token
        except requests.RequestException as e:
            logger.error("Failed to authenticate with MemReport at %s: %s", url, e)
            raise ConnectionError(f"MemReport login failed at {url}: {e}") from e

    def upload_report(
        self,
        date_str: str,
        content: str,
        content_type: str = "markdown",
        overwrite: bool = True,
    ) -> dict[str, Any]:
        """Uploads or appends a markdown report for a given date."""
        if not self.token:
            self.login()

        url = f"{self.base_url}/api/reports/{date_str}"
        params = {"overwrite": "true" if overwrite else "false"}
        payload = {"content": content, "content_type": content_type}

        try:
            res = self.session.post(url, params=params, json=payload, timeout=15)
            res.raise_for_status()
            data = res.json()
            logger.info("Uploaded report for %s to MemReport (%d bytes)", date_str, len(content))
            return data
        except requests.RequestException as e:
            logger.error("Failed to upload report for %s to %s: %s", date_str, url, e)
            raise ConnectionError(f"MemReport upload failed for {date_str}: {e}") from e

    def set_location(
        self,
        date_str: str,
        latitude: float,
        longitude: float,
        name: str | None = None,
    ) -> dict[str, Any]:
        """Sets the daily GPS pin location in MemReport."""
        if not self.token:
            self.login()

        url = f"{self.base_url}/api/reports/{date_str}/location"
        payload = {"latitude": latitude, "longitude": longitude, "name": name}

        try:
            res = self.session.put(url, json=payload, timeout=10)
            res.raise_for_status()
            data = res.json()
            logger.info("Set GPS location for %s to (%s, %s) in MemReport", date_str, latitude, longitude)
            return data
        except requests.RequestException as e:
            logger.warning("Failed setting GPS location for %s in MemReport: %s", date_str, e)
            return {}

    def upload_file(
        self,
        file_path: Path | str,
        date_str: str,
        latitude: float | None = None,
        longitude: float | None = None,
        location_name: str | None = None,
    ) -> dict[str, Any]:
        """Convenience method to upload a local markdown file and optional coordinates."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Report file not found: {path}")

        content = path.read_text(encoding="utf-8")
        result = self.upload_report(date_str, content, overwrite=True)

        if latitude is not None and longitude is not None:
            self.set_location(date_str, latitude, longitude, name=location_name)

        return result
