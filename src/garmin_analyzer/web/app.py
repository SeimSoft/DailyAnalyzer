"""FastAPI Web Application for Garmin Analyzer.

Allows password-protected activity browsing (last 100 activities with photos),
interactive report generation (AI storytelling), and automated upload to MemReport.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import secrets
import threading
import time
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import (
    Cookie,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from garmin_analyzer.auth import get_authenticated_client
from garmin_analyzer.client import GarminAnalyzer
from garmin_analyzer.models import ActivityOverview
from garmin_analyzer.uploader import (
    DEFAULT_MEMREPORT_URL,
    DEFAULT_PASSWORD,
    DEFAULT_USERNAME,
    MemReportClient,
)

logger = logging.getLogger(__name__)

# --- Environment & Configuration ---
DEFAULT_ADMIN_PASSWORD = os.getenv("WEB_ADMIN_PASSWORD") or os.getenv("ADMIN_PASSWORD") or "admin123"
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "today"))
TOKEN_DIR = Path(os.getenv("GARMIN_TOKEN_DIR", Path.home() / ".garminconnect_tokens"))

# In-memory session and job store
_active_sessions: set[str] = set()
_revoked_sessions: set[str] = set()
_activities_cache: dict[str, Any] = {}
_cache_lock = threading.Lock()

# Jobs store: job_id -> JobState
_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()


# --- Models ---
class LoginRequest(BaseModel):
    password: str


class GenerateRequest(BaseModel):
    dates: list[str] = Field(default_factory=list)
    activity_ids: list[int] = Field(default_factory=list)
    notes: dict[str, str] = Field(default_factory=dict)
    llm_summary: bool = True
    upload: bool = True
    memreport_url: str | None = None
    memreport_user: str | None = None
    memreport_pass: str | None = None


# --- FastAPI App ---
app = FastAPI(
    title="Garmin Analyzer Web",
    description="Web interface for browsing Garmin activities with photos, generating AI reports, and uploading to MemReport.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Auth Helpers ---
def _get_auth_secret() -> bytes:
    expected_password = (
        os.getenv("WEB_ADMIN_PASSWORD")
        or os.getenv("ADMIN_PASSWORD")
        or DEFAULT_ADMIN_PASSWORD
    )
    return hashlib.sha256(f"garmin_analyzer_session_{expected_password}".encode()).digest()


def _create_session_token() -> str:
    ts = str(int(time.time()))
    sig = hmac.new(_get_auth_secret(), ts.encode(), hashlib.sha256).hexdigest()
    return f"{ts}.{sig}"


def _is_valid_token(token: str | None) -> bool:
    if not token or token in _revoked_sessions:
        return False
    if token in _active_sessions:
        return True
    try:
        parts = token.split(".", 1)
        if len(parts) != 2:
            return False
        ts_str, sig = parts
        expected_sig = hmac.new(_get_auth_secret(), ts_str.encode(), hashlib.sha256).hexdigest()
        if not secrets.compare_digest(sig, expected_sig):
            return False
        ts = int(ts_str)
        now = time.time()
        # Valid for 7 days, allow up to 60s clock skew
        if now - ts > 86400 * 7 or now < ts - 60:
            return False
        return True
    except Exception:
        return False


def verify_session(
    session_token: str | None = Cookie(default=None),
    authorization: str | None = None,
) -> bool:
    """Validates session token from cookie or Authorization header."""
    token = session_token
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()

    if not token or not _is_valid_token(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please enter the admin password.",
        )
    return True


# --- API Endpoints ---
@app.post("/api/auth/login")
def login(req: LoginRequest, response: Response) -> dict[str, Any]:
    """Authenticates using admin password and sets HTTP session cookie."""
    expected_password = (
        os.getenv("WEB_ADMIN_PASSWORD")
        or os.getenv("ADMIN_PASSWORD")
        or DEFAULT_ADMIN_PASSWORD
    )
    if not secrets.compare_digest(req.password, expected_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falsches Admin-Passwort.",
        )

    token = _create_session_token()
    _active_sessions.add(token)
    if token in _revoked_sessions:
        _revoked_sessions.remove(token)

    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=86400 * 7,  # 7 days
    )
    return {"success": True, "token": token}


@app.post("/api/auth/logout")
def logout(response: Response, session_token: str | None = Cookie(default=None)) -> dict[str, Any]:
    """Logs out and invalidates current session token."""
    if session_token:
        _revoked_sessions.add(session_token)
        if session_token in _active_sessions:
            _active_sessions.remove(session_token)
    response.delete_cookie("session_token")
    return {"success": True}


@app.get("/api/auth/status")
def auth_status(
    session_token: str | None = Cookie(default=None),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Returns current authentication state and service configurations."""
    token = session_token
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()

    is_authenticated = bool(token and _is_valid_token(token))
    has_gemini = bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
    memreport_url = os.getenv("MEMREPORT_URL", DEFAULT_MEMREPORT_URL)
    memreport_user = os.getenv("MEMREPORT_USER", DEFAULT_USERNAME)

    return {
        "authenticated": is_authenticated,
        "memreport_url": memreport_url,
        "memreport_user": memreport_user,
        "has_gemini_key": has_gemini,
    }


@app.get("/api/activities", dependencies=[Depends(verify_session)])
def list_activities(
    limit: int = Query(default=100, ge=1, le=500),
    start: int = Query(default=0, ge=0),
    refresh: bool = Query(default=False),
    only_with_photos: bool = Query(default=True),
) -> dict[str, Any]:
    """Fetches recent activities with pagination, optionally filtering to those with photos."""
    global _activities_cache
    cache_key = f"{start}_{limit}_{only_with_photos}"

    with _cache_lock:
        if not refresh and cache_key in _activities_cache:
            cached_entry = _activities_cache[cache_key]
            return {
                "activities": cached_entry["data"],
                "total_inspected": cached_entry.get("total_inspected", 0),
                "start": start,
                "limit": limit,
                "has_more": cached_entry.get("has_more", False),
                "cached": True,
            }

    try:
        client = get_authenticated_client(token_dir=TOKEN_DIR)
        analyzer = GarminAnalyzer(client)
        raw_activities = analyzer.get_recent_activities(limit=limit, start_index=start)
        if not raw_activities:
            return {
                "activities": [],
                "total_inspected": 0,
                "start": start,
                "limit": limit,
                "has_more": False,
                "cached": False,
            }

        parsed = [analyzer.parse_activity(a) for a in raw_activities]
        analyzer.check_activities_photos(parsed)

        filtered = [a for a in parsed if a.photos_count > 0] if only_with_photos else parsed

        # Check uploaded reports in MemReport
        uploaded_dates: set[str] = set()
        memreport_client = MemReportClient()
        try:
            uploaded_dates = memreport_client.get_uploaded_dates()
        except Exception as err:
            logger.debug("Could not determine uploaded dates from MemReport: %s", err)

        data = [
            {
                "activity_id": act.activity_id,
                "date": act.date_str,
                "name": act.activity_name,
                "type": act.activity_type,
                "sub_sport": act.activity_sub_sport,
                "description": act.description,
                "distance_km": act.stats.distance_km,
                "duration": act.stats.duration_formatted,
                "avg_hr": act.stats.average_hr,
                "photos_count": act.photos_count,
                "location_name": act.location.location_name,
                "memreport_uploaded": act.date_str in uploaded_dates,
                "viewer_url": f"{memreport_client.base_url}/viewer?date={act.date_str}"
                if act.date_str in uploaded_dates
                else None,
            }
            for act in filtered
        ]

        has_more = len(raw_activities) == limit

        with _cache_lock:
            _activities_cache[cache_key] = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": data,
                "total_inspected": len(raw_activities),
                "has_more": has_more,
            }

        return {
            "activities": data,
            "total_inspected": len(raw_activities),
            "start": start,
            "limit": limit,
            "has_more": has_more,
            "cached": False,
        }
    except Exception as e:
        logger.error("Failed loading Garmin activities: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Garmin Aktivitäten konnten nicht geladen werden: {e}",
        ) from e


# --- Background Job Execution ---
def _run_report_job(job_id: str, req: GenerateRequest) -> None:
    """Executes report generation and MemReport upload for selected dates."""

    def log(message: str) -> None:
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job:
                job["logs"].append(
                    {"timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S"), "message": message}
                )

    log(f"🚀 Job {job_id[:8]} gestartet für {len(req.dates)} Tag(e)...")

    memreport_url = req.memreport_url or os.getenv("MEMREPORT_URL", DEFAULT_MEMREPORT_URL)
    memreport_user = req.memreport_user or os.getenv("MEMREPORT_USER", DEFAULT_USERNAME)
    memreport_pass = req.memreport_pass or os.getenv("MEMREPORT_PASSWORD", DEFAULT_PASSWORD)

    results: list[dict[str, Any]] = []

    try:
        client = get_authenticated_client(token_dir=TOKEN_DIR)
        analyzer = GarminAnalyzer(client)

        total_dates = len(req.dates)
        for idx, date_str in enumerate(req.dates, 1):
            date_notes = req.notes.get(date_str)
            if date_notes:
                log(f"[{idx}/{total_dates}] 📝 Notiz erfasst: '{date_notes}'")
            log(f"[{idx}/{total_dates}] 📥 Lade Daten für {date_str} herunter...")

            try:
                daily_summary, downloaded_activities, diary_path = analyzer.download_daily(
                    date_str,
                    output_dir=OUTPUT_DIR,
                    include_activities=True,
                    include_tracks=True,
                    include_photos=True,
                    generate_llm_summary=req.llm_summary,
                    user_notes=date_notes,
                    force=True,
                )

                log(
                    f"[{idx}/{total_dates}] ✓ {len(downloaded_activities)} Aktivität(en) heruntergeladen."
                )

                # Report File to upload
                report_file = diary_path if (diary_path and diary_path.exists()) else None
                if not report_file:
                    fallback_md = OUTPUT_DIR / "daily_health" / date_str / "daily_summary.md"
                    if fallback_md.exists():
                        report_file = fallback_md

                uploaded = False
                memreport_view_url = None

                if req.upload and report_file and report_file.exists():
                    log(f"[{idx}/{total_dates}] 📤 Lade Report zu MemReport hoch ({memreport_url})...")
                    uploader = MemReportClient(
                        base_url=memreport_url,
                        username=memreport_user,
                        password=memreport_pass,
                    )
                    content = report_file.read_text(encoding="utf-8")
                    uploader.upload_report(date_str, content=content, overwrite=True)

                    # Set GPS coordinates if available
                    for da in downloaded_activities:
                        if da.overview.location.has_coordinates:
                            lat = da.overview.location.start_latitude
                            lon = da.overview.location.start_longitude
                            loc_name = da.overview.location.location_name or da.overview.activity_name
                            uploader.set_location(date_str, lat, lon, name=loc_name)
                            break

                    uploaded = True
                    memreport_view_url = f"{uploader.base_url}/viewer?date={date_str}"
                    log(f"[{idx}/{total_dates}] ✨ Erfolgreich in MemReport bereitgestellt: {date_str}")

                results.append(
                    {
                        "date": date_str,
                        "success": True,
                        "uploaded": uploaded,
                        "report_file": str(report_file) if report_file else None,
                        "viewer_url": memreport_view_url,
                    }
                )

            except Exception as item_err:
                log(f"[{idx}/{total_dates}] ❌ Fehler für {date_str}: {item_err}")
                results.append({"date": date_str, "success": False, "error": str(item_err)})

            # Update progress
            with _jobs_lock:
                job = _jobs.get(job_id)
                if job:
                    job["progress"] = int((idx / total_dates) * 100)

        log("🎉 Alle Aufgaben abgeschlossen!")

        with _jobs_lock:
            job = _jobs.get(job_id)
            if job:
                job["status"] = "completed"
                job["results"] = results
                job["progress"] = 100

        with _cache_lock:
            _activities_cache["data"] = []

    except Exception as e:
        log(f"💥 Kritischer Fehler im Job: {e}")
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job:
                job["status"] = "failed"
                job["error"] = str(e)


@app.post("/api/generate", dependencies=[Depends(verify_session)])
def start_generation_job(req: GenerateRequest) -> dict[str, Any]:
    """Starts asynchronous report generation and upload job."""
    if not req.dates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mindestens ein Datum / eine Aktivität muss ausgewählt werden.",
        )

    job_id = str(uuid.uuid4())
    with _jobs_lock:
        _jobs[job_id] = {
            "job_id": job_id,
            "status": "running",
            "progress": 0,
            "logs": [],
            "results": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    thread = threading.Thread(target=_run_report_job, args=(job_id, req), daemon=True)
    thread.start()

    return {"job_id": job_id, "status": "running"}


@app.get("/api/jobs/{job_id}", dependencies=[Depends(verify_session)])
def get_job_status(job_id: str) -> dict[str, Any]:
    """Retrieves execution status, logs, and results for a job."""
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job {job_id} nicht gefunden.",
            )
        return dict(job)


@app.get("/api/jobs/{job_id}/stream", dependencies=[Depends(verify_session)])
async def stream_job_events(job_id: str) -> StreamingResponse:
    """Streams server-sent events for a running job."""

    async def event_generator() -> AsyncGenerator[str, None]:
        last_log_idx = 0
        while True:
            with _jobs_lock:
                job = _jobs.get(job_id)
                if not job:
                    yield f"data: {json.dumps({'error': 'Job not found'})}\n\n"
                    break

                logs = job.get("logs", [])
                status = job.get("status", "unknown")
                progress = job.get("progress", 0)
                results = job.get("results", [])

                new_logs = logs[last_log_idx:]
                last_log_idx = len(logs)

            for item in new_logs:
                yield f"data: {json.dumps({'type': 'log', 'log': item, 'progress': progress, 'status': status})}\n\n"

            if status in ("completed", "failed"):
                yield f"data: {json.dumps({'type': 'done', 'status': status, 'progress': progress, 'results': results})}\n\n"
                break

            await asyncio.sleep(0.8)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# --- HTML Frontend Route ---
@app.get("/", response_class=HTMLResponse)
def serve_index() -> HTMLResponse:
    """Serves the unified single-page web UI."""
    html_file = Path(__file__).parent / "static" / "index.html"
    if html_file.exists():
        return HTMLResponse(content=html_file.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Garmin Analyzer Web UI is loading...</h1>")
