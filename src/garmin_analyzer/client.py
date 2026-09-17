"""High-level client orchestrating activity and daily health data downloads."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import io
import json
import logging
import re
import zipfile
from pathlib import Path
from typing import Any

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
)
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from garmin_analyzer.daily import fetch_daily_health, parse_date_input
from garmin_analyzer.evaluator import evaluate_daily_health, save_evaluations
from garmin_analyzer.formatter import (
    format_activity_markdown,
    format_daily_markdown,
)
from garmin_analyzer.gps_map import render_gps_map
from garmin_analyzer.models import (
    ActivityOverview,
    DailyHealthSummary,
    DownloadedActivity,
    LocationInfo,
    PerformanceStats,
    SplitInfo,
    WeatherInfo,
)
from garmin_analyzer.photos import (
    download_photo,
    extract_photos_from_activity_dict,
    fetch_activity_photos_from_api,
)
from garmin_analyzer.storyteller import generate_self_contained_daily_story
from garmin_analyzer.visualizer import generate_all_daily_visualizations

logger = logging.getLogger(__name__)


def slugify(text: str) -> str:
    """Converts a title into a filesystem-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "_", text)
    return text[:50] or "activity"


class GarminAnalyzer:
    """Orchestrates downloading Garmin activities, tracks, health stats, and photos."""

    def __init__(self, client: Garmin, console: Console | None = None):
        self.client = client
        self.console = console or Console()
        self._daily_cache: dict[str, DailyHealthSummary] = {}

    def parse_activity(self, data: dict[str, Any]) -> ActivityOverview:
        """Parses raw Garmin activity dictionary into structured ActivityOverview."""
        activity_id = data.get("activityId") or data.get("activityID")
        if not activity_id:
            raise ValueError("Activity dictionary does not contain an activityId")

        activity_name = data.get("activityName") or f"Activity {activity_id}"
        activity_type_dto = data.get("activityType") or {}
        if isinstance(activity_type_dto, dict):
            activity_type = activity_type_dto.get("typeKey") or "other"
        else:
            activity_type = str(activity_type_dto or "other")

        event_type_dto = data.get("eventType") or {}
        event_type = event_type_dto.get("typeKey") if isinstance(event_type_dto, dict) else None

        start_time_local = data.get("startTimeLocal") or ""
        start_time_gmt = data.get("startTimeGMT")

        # Location
        location = LocationInfo(
            start_latitude=data.get("startLatitude"),
            start_longitude=data.get("startLongitude"),
            end_latitude=data.get("endLatitude"),
            end_longitude=data.get("endLongitude"),
            min_elevation_meters=data.get("minElevation"),
            max_elevation_meters=data.get("maxElevation"),
            location_name=data.get("locationName"),
            course_id=str(data.get("associatedCourseId"))
            if data.get("associatedCourseId")
            else None,
        )

        # Performance stats
        stats = PerformanceStats(
            distance_meters=float(data.get("distance") or 0.0),
            duration_seconds=float(data.get("duration") or 0.0),
            elapsed_seconds=float(data.get("elapsedDuration"))
            if data.get("elapsedDuration") is not None
            else None,
            moving_duration_seconds=float(data.get("movingDuration"))
            if data.get("movingDuration") is not None
            else None,
            calories=data.get("calories"),
            average_hr=data.get("averageHR"),
            max_hr=data.get("maxHR"),
            avg_speed_mps=data.get("averageSpeed"),
            max_speed_mps=data.get("maxSpeed"),
            elevation_gain_meters=data.get("elevationGain"),
            elevation_loss_meters=data.get("elevationLoss"),
            avg_cadence=data.get("averageRunningCadenceInStepsPerMinute")
            or data.get("averageBikingCadenceInRevPerMinute"),
            max_cadence=data.get("maxRunningCadenceInStepsPerMinute")
            or data.get("maxBikingCadenceInRevPerMinute"),
            avg_power=data.get("avgPower"),
            max_power=data.get("maxPower"),
            normalized_power=data.get("normPower"),
            vo2_max=data.get("vO2MaxValue"),
            aerobic_training_effect=data.get("aerobicTrainingEffect"),
            anaerobic_training_effect=data.get("anaerobicTrainingEffect"),
            avg_temperature_c=data.get("avgTemperature"),
        )

        # Photos count if present in metadataDTO or activity dict
        metadata = data.get("metadataDTO") or {}
        photos_count = data.get("photos_count", 0)
        if isinstance(metadata, dict):
            activity_images = metadata.get("activityImages") or metadata.get("photos") or []
            if isinstance(activity_images, list) and activity_images:
                photos_count = max(photos_count, len(activity_images))

        return ActivityOverview(
            activity_id=int(activity_id),
            activity_name=activity_name,
            activity_type=activity_type,
            activity_type_key=activity_type,
            activity_sub_sport=data.get("activitySubSport"),
            description=data.get("description"),
            event_type=event_type,
            start_time_local=start_time_local,
            start_time_gmt=start_time_gmt,
            location=location,
            stats=stats,
            photos_count=photos_count,
        )

    def get_recent_activities(
        self,
        limit: int = 10,
        start_index: int = 0,
        activity_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetches list of activity summaries from Garmin API."""
        try:
            if activity_type:
                activities = self.client.get_activities(
                    start_index, limit, activitytype=activity_type
                )
            else:
                activities = self.client.get_activities(start_index, limit)
            return activities or []
        except (GarminConnectConnectionError, GarminConnectAuthenticationError, OSError) as e:
            logger.error("Failed to retrieve activities: %s", e)
            return []

    def check_activities_photos(
        self,
        activities: list[ActivityOverview],
        max_workers: int = 20,
    ) -> list[ActivityOverview]:
        """Checks and populates photos_count for each activity using parallel requests."""
        if not activities:
            return activities

        def check_one(act: ActivityOverview) -> tuple[int, int]:
            try:
                detail = self.client.get_activity(act.activity_id)
                photos = extract_photos_from_activity_dict(detail)
                return act.activity_id, len(photos)
            except Exception as e:
                logger.debug("Failed to inspect photos for activity %s: %s", act.activity_id, e)
                return act.activity_id, 0

        counts: dict[int, int] = {}
        with ThreadPoolExecutor(max_workers=min(max_workers, len(activities))) as executor:
            future_to_id = {executor.submit(check_one, act): act.activity_id for act in activities}
            for future in as_completed(future_to_id):
                act_id, count = future.result()
                counts[act_id] = count

        for act in activities:
            act.photos_count = counts.get(act.activity_id, 0)

        return activities

    def download_activity(
        self,
        raw_activity: dict[str, Any],
        output_dir: Path,
        include_tracks: bool = True,
        include_photos: bool = True,
        include_daily: bool = True,
        force: bool = False,
    ) -> DownloadedActivity:
        """Downloads full telemetry, GPS tracks, photos, and daily health for a single activity."""
        overview = self.parse_activity(raw_activity)
        activity_id = overview.activity_id
        date_slug = overview.date_str
        name_slug = slugify(overview.activity_name)

        act_dir = output_dir / "activities" / f"{date_slug}_{activity_id}_{name_slug}"
        act_dir.mkdir(parents=True, exist_ok=True)
        files_saved: list[str] = []

        # 1. Enrich raw_activity with full activity metadata (e.g. metadataDTO with activityImages)
        if include_photos or "metadataDTO" not in raw_activity:
            try:
                full_act = self.client.get_activity(activity_id)
                if full_act and isinstance(full_act, dict):
                    raw_activity = {**raw_activity, **full_act}
            except (GarminConnectConnectionError, OSError, ValueError, KeyError) as e:
                logger.debug("Could not fetch full activity for %s: %s", activity_id, e)

        # 1. Save raw activity metadata JSON
        raw_path = act_dir / "raw_activity.json"
        if force or not raw_path.exists():
            raw_path.write_text(json.dumps(raw_activity, indent=2, ensure_ascii=False))
        files_saved.append(str(raw_path))

        # 2. Fetch full activity details & telemetry
        details_json = None
        details_path = act_dir / "raw_details.json"
        try:
            if force or not details_path.exists():
                details_json = self.client.get_activity_details(activity_id)
                if details_json:
                    details_path.write_text(json.dumps(details_json, indent=2, ensure_ascii=False))
                    files_saved.append(str(details_path))
            elif details_path.exists():
                details_json = json.loads(details_path.read_text())
        except (GarminConnectConnectionError, OSError) as e:
            logger.debug("Activity details not available for %s: %s", activity_id, e)

        # 3. Fetch splits
        splits_path = act_dir / "splits.json"
        try:
            if force or not splits_path.exists():
                splits_data = self.client.get_activity_splits(activity_id)
                if splits_data:
                    splits_path.write_text(json.dumps(splits_data, indent=2, ensure_ascii=False))
                    files_saved.append(str(splits_path))
                    # Parse into SplitInfo list
                    split_items = (
                        splits_data.get("lapDTOs") or splits_data.get("splitSummaries") or []
                    )
                    overview.splits = [
                        SplitInfo(
                            split_index=idx + 1,
                            distance_meters=float(s.get("distance") or 0.0),
                            duration_seconds=float(s.get("duration") or 0.0),
                            avg_speed_mps=s.get("averageSpeed"),
                            avg_hr=s.get("averageHR"),
                            max_hr=s.get("maxHR"),
                            elevation_gain_meters=s.get("elevationGain"),
                            elevation_loss_meters=s.get("elevationLoss"),
                            calories=s.get("calories"),
                        )
                        for idx, s in enumerate(split_items)
                        if isinstance(s, dict)
                    ]
        except (GarminConnectConnectionError, OSError) as e:
            logger.debug("Splits not available for %s: %s", activity_id, e)

        # 4. Fetch weather
        weather_path = act_dir / "weather.json"
        try:
            if force or not weather_path.exists():
                weather_data = self.client.get_activity_weather(activity_id)
                if weather_data:
                    weather_path.write_text(json.dumps(weather_data, indent=2, ensure_ascii=False))
                    files_saved.append(str(weather_path))
                    overview.weather = WeatherInfo(
                        temperature_c=weather_data.get("temp"),
                        relative_humidity=weather_data.get("relativeHumidity"),
                        wind_speed_mps=weather_data.get("windSpeed"),
                        wind_direction_compass=weather_data.get("windDirectionCompassPoint"),
                        weather_condition=weather_data.get("weatherCondition"),
                        issue_time=weather_data.get("issueTime"),
                    )
        except (GarminConnectConnectionError, OSError) as e:
            logger.debug("Weather not available for %s: %s", activity_id, e)

        # 5. Fetch HR zones
        hr_zones_path = act_dir / "hr_zones.json"
        try:
            if force or not hr_zones_path.exists():
                hr_zones = self.client.get_activity_hr_in_timezones(activity_id)
                if hr_zones:
                    hr_zones_path.write_text(json.dumps(hr_zones, indent=2, ensure_ascii=False))
                    files_saved.append(str(hr_zones_path))
                    overview.hr_zones = hr_zones
        except (GarminConnectConnectionError, OSError) as e:
            logger.debug("HR zones not available for %s: %s", activity_id, e)

        # 6. Download GPS Tracks (GPX, TCX, FIT)
        track_gpx_path = None
        track_tcx_path = None
        track_fit_path = None

        if include_tracks:
            # GPX
            gpx_file = act_dir / "track.gpx"
            if force or not gpx_file.exists():
                try:
                    data = self.client.download_activity(
                        activity_id, dl_fmt=self.client.ActivityDownloadFormat.GPX
                    )
                    if data:
                        gpx_file.write_bytes(data)
                except (GarminConnectConnectionError, OSError) as e:
                    logger.debug("GPX download not available for %s: %s", activity_id, e)
            if gpx_file.exists():
                track_gpx_path = str(gpx_file)
                files_saved.append(str(gpx_file))

            # TCX
            tcx_file = act_dir / "track.tcx"
            if force or not tcx_file.exists():
                try:
                    data = self.client.download_activity(
                        activity_id, dl_fmt=self.client.ActivityDownloadFormat.TCX
                    )
                    if data:
                        tcx_file.write_bytes(data)
                except (GarminConnectConnectionError, OSError) as e:
                    logger.debug("TCX download not available for %s: %s", activity_id, e)
            if tcx_file.exists():
                track_tcx_path = str(tcx_file)
                files_saved.append(str(tcx_file))

            # Original FIT
            fit_file = act_dir / "track.fit"
            if force or not fit_file.exists():
                try:
                    data = self.client.download_activity(
                        activity_id, dl_fmt=self.client.ActivityDownloadFormat.ORIGINAL
                    )
                    if data:
                        # If returned data is a zip archive, extract the .fit file
                        if data[:2] == b"PK":
                            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                                for member in zf.namelist():
                                    if member.endswith(".fit"):
                                        fit_file.write_bytes(zf.read(member))
                                        break
                                else:
                                    fit_file.write_bytes(data)
                        else:
                            fit_file.write_bytes(data)
                except (GarminConnectConnectionError, OSError) as e:
                    logger.debug("FIT download not available for %s: %s", activity_id, e)
            if fit_file.exists():
                track_fit_path = str(fit_file)
                files_saved.append(str(fit_file))

            # Render GPS Route Map if GPX track is available
            gpx_file = act_dir / "track.gpx"
            if gpx_file.exists():
                map_file = act_dir / "gps_map.png"
                if force or not map_file.exists():
                    try:
                        render_gps_map(
                            gpx_file,
                            map_file,
                            title=overview.activity_name,
                            distance_km=overview.stats.distance_km,
                            elevation_gain_m=overview.stats.elevation_gain_meters,
                        )
                    except (OSError, ValueError, RuntimeError) as e:
                        logger.debug("GPS map rendering failed for %s: %s", activity_id, e)
                if map_file.exists():
                    files_saved.append(str(map_file))

        # 7. Discover and Download Uploaded Photos
        downloaded_photos = []
        if include_photos:
            photos_dir = act_dir / "photos"
            candidate_photos = extract_photos_from_activity_dict(raw_activity)
            if details_json and isinstance(details_json, dict):
                candidate_photos.extend(extract_photos_from_activity_dict(details_json))

            # Deduplicate by photo_id
            seen_ids = set()
            unique_photos = []
            for p in candidate_photos:
                if p.photo_id not in seen_ids:
                    seen_ids.add(p.photo_id)
                    unique_photos.append(p)

            for idx, photo in enumerate(unique_photos, 1):
                local_path = download_photo(self.client, photo, photos_dir, index=idx)
                if local_path:
                    downloaded_photos.append(photo)
                    files_saved.append(str(local_path))

        # 8. Daily Health Stats (7-Day Trends & Context for That Day)
        daily_health = None
        if include_daily:
            daily_health = self.get_or_fetch_daily_health(
                overview.date_str, output_dir=output_dir, force=force
            )

        # 9. Save Curated Activity Summary JSON and Markdown
        downloaded_activity = DownloadedActivity(
            overview=overview,
            directory=str(act_dir),
            track_gpx_path=track_gpx_path,
            track_tcx_path=track_tcx_path,
            track_fit_path=track_fit_path,
            photos=downloaded_photos,
            daily_health=daily_health,
            files_saved=files_saved,
        )

        summary_json_path = act_dir / "activity_summary.json"
        summary_json_path.write_text(downloaded_activity.model_dump_json(indent=2))
        files_saved.append(str(summary_json_path))

        summary_md_path = act_dir / "activity_summary.md"
        summary_md_path.write_text(format_activity_markdown(downloaded_activity))
        files_saved.append(str(summary_md_path))

        return downloaded_activity

    def get_or_fetch_daily_health(
        self,
        date_str: str,
        output_dir: Path,
        force: bool = False,
    ) -> DailyHealthSummary:
        """Fetches and saves daily health stats for a specific date, caching in-memory and on disk."""
        canonical_date, _ = parse_date_input(date_str)
        daily_dir = output_dir / "daily_health" / canonical_date
        daily_json = daily_dir / "daily_summary.json"

        if not force and canonical_date in self._daily_cache:
            return self._daily_cache[canonical_date]

        if not force and daily_json.exists():
            try:
                summary = DailyHealthSummary.model_validate_json(daily_json.read_text())
                self._daily_cache[canonical_date] = summary
                return summary
            except (json.JSONDecodeError, OSError, ValueError) as err:
                logger.debug("Failed reading cached daily json: %s", err)

        daily_dir.mkdir(parents=True, exist_ok=True)
        summary, raw_data = fetch_daily_health(self.client, canonical_date)

        daily_json.write_text(summary.model_dump_json(indent=2))
        (daily_dir / "raw_daily.json").write_text(
            json.dumps(raw_data, indent=2, ensure_ascii=False)
        )
        (daily_dir / "daily_summary.md").write_text(format_daily_markdown(summary))

        # Generate condensed health judgments and evaluations
        try:
            evaluation = evaluate_daily_health(summary)
            save_evaluations(evaluation, daily_dir)
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as err:
            logger.warning("Failed saving evaluations for %s: %s", canonical_date, err)

        # Generate health visualizations (heart rate, stress, body battery, HRV vs time)
        try:
            generate_all_daily_visualizations(raw_data, daily_dir)
        except (OSError, ValueError, KeyError, TypeError, AttributeError, RuntimeError) as err:
            logger.warning("Failed generating charts for %s: %s", canonical_date, err)

        self._daily_cache[canonical_date] = summary
        return summary

    def get_activities_for_date(self, date_str: str) -> list[dict[str, Any]]:
        """Fetches raw activity dictionaries for a specific calendar date (YYYY-MM-DD)."""
        canonical_date, _ = parse_date_input(date_str)
        try:
            acts = self.client.get_activities_by_date(canonical_date, canonical_date)
            if not acts:
                fordate_res = self.client.get_activities_fordate(canonical_date)
                if isinstance(fordate_res, list):
                    acts = fordate_res
                elif isinstance(fordate_res, dict) and "Activities" in fordate_res:
                    acts = fordate_res.get("Activities") or []
            return acts or []
        except (GarminConnectConnectionError, GarminConnectAuthenticationError, OSError) as e:
            logger.error("Failed to retrieve activities for %s: %s", canonical_date, e)
            return []

    def download_daily(
        self,
        date_str: str,
        output_dir: Path | str = Path("./garmin_data"),
        include_activities: bool = True,
        include_tracks: bool = True,
        include_photos: bool = True,
        generate_llm_summary: bool = False,
        user_notes: str | None = None,
        force: bool = False,
    ) -> tuple[DailyHealthSummary, list[DownloadedActivity], Path | None]:
        """Downloads full daily health metrics, charts, evaluations, and any activities that occurred on that day."""
        output_path = Path(output_dir).expanduser().resolve()
        canonical_date, _ = parse_date_input(date_str)

        # 1. Fetch or load daily health stats
        summary = self.get_or_fetch_daily_health(
            canonical_date, output_dir=output_path, force=force
        )

        downloaded_activities: list[DownloadedActivity] = []

        # 2. Fetch and download activities for that day
        if include_activities:
            raw_activities = self.get_activities_for_date(canonical_date)
            for raw_act in raw_activities:
                try:
                    act_down = self.download_activity(
                        raw_act,
                        output_dir=output_path,
                        include_tracks=include_tracks,
                        include_photos=include_photos,
                        include_daily=False,
                        force=force,
                    )
                    act_down.daily_health = summary
                    downloaded_activities.append(act_down)
                    if not any(
                        a.activity_id == act_down.overview.activity_id for a in summary.activities
                    ):
                        summary.activities.append(act_down.overview)
                except (
                    GarminConnectConnectionError,
                    GarminConnectAuthenticationError,
                    OSError,
                    ValueError,
                    KeyError,
                ) as err:
                    logger.warning("Failed downloading activity from %s: %s", canonical_date, err)

            # Update daily_summary.json and daily_summary.md with downloaded activities
            daily_dir = output_path / "daily_health" / canonical_date
            daily_json = daily_dir / "daily_summary.json"
            daily_md = daily_dir / "daily_summary.md"
            daily_json.write_text(summary.model_dump_json(indent=2))
            daily_md.write_text(format_daily_markdown(summary))
            self._daily_cache[canonical_date] = summary

        # 3. Generate AI personal diary entry if requested
        diary_path: Path | None = None
        if generate_llm_summary:
            daily_dir = output_path / "daily_health" / canonical_date
            act_dirs = [Path(da.directory) for da in downloaded_activities]
            try:
                diary_path, _ = generate_self_contained_daily_story(
                    canonical_date,
                    daily_dir=daily_dir,
                    activity_dirs=act_dirs,
                    user_notes=user_notes,
                )
            except (OSError, ValueError, RuntimeError, KeyError) as err:
                logger.warning("Failed generating AI daily diary for %s: %s", canonical_date, err)

        return summary, downloaded_activities, diary_path

    def download_batch(
        self,
        limit: int = 10,
        activity_type: str | None = None,
        output_dir: Path | str = Path("./garmin_data"),
        include_tracks: bool = True,
        include_photos: bool = True,
        include_daily: bool = True,
        force: bool = False,
    ) -> list[DownloadedActivity]:
        """Downloads recent activities in batch with progress visualization."""
        output_path = Path(output_dir).expanduser().resolve()
        output_path.mkdir(parents=True, exist_ok=True)

        self.console.print(f"[bold cyan]Fetching up to {limit} recent activities...[/bold cyan]")
        raw_activities = self.get_recent_activities(limit=limit, activity_type=activity_type)

        if not raw_activities:
            self.console.print("[yellow]No activities found matching criteria.[/yellow]")
            return []

        results: list[DownloadedActivity] = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console,
        ) as progress:
            task = progress.add_task(
                f"[cyan]Downloading {len(raw_activities)} activities...",
                total=len(raw_activities),
            )

            for act_dict in raw_activities:
                act_id = act_dict.get("activityId")
                act_name = act_dict.get("activityName", str(act_id))
                progress.update(
                    task,
                    description=f"[cyan]Downloading activity [bold]{act_name}[/bold] ({act_id})...",
                )

                try:
                    downloaded = self.download_activity(
                        act_dict,
                        output_dir=output_path,
                        include_tracks=include_tracks,
                        include_photos=include_photos,
                        include_daily=include_daily,
                        force=force,
                    )
                    results.append(downloaded)
                except Exception as e:
                    logger.exception("Error processing activity %s", act_id)
                    self.console.print(f"[red]Failed downloading activity {act_id}: {e}[/red]")

                progress.advance(task)

        # Write index files
        self._write_indexes(results, output_path)
        self.console.print(
            f"[green]✓ Completed download of {len(results)} activities into [bold]{output_path}[/bold][/green]"
        )
        return results

    def _write_indexes(self, activities: list[DownloadedActivity], output_dir: Path) -> None:
        """Writes activities_index.json and activities_index.csv."""
        index_data = []
        for a in activities:
            o = a.overview
            s = o.stats
            l = o.location
            d = a.daily_health
            index_data.append(
                {
                    "activity_id": o.activity_id,
                    "name": o.activity_name,
                    "date": o.date_str,
                    "type": o.activity_type,
                    "distance_km": s.distance_km,
                    "duration": s.duration_formatted,
                    "avg_pace": s.avg_pace_min_per_km or "",
                    "avg_speed_kmh": s.avg_speed_kmh or "",
                    "avg_hr": s.average_hr or "",
                    "calories": s.calories or "",
                    "elevation_gain_m": s.elevation_gain_meters or "",
                    "latitude": l.start_latitude or "",
                    "longitude": l.start_longitude or "",
                    "photos_count": len(a.photos),
                    "track_gpx": a.track_gpx_path or "",
                    "track_fit": a.track_fit_path or "",
                    "resting_hr": d.resting_hr if d else "",
                    "rhr_7d_avg": d.rhr_7day_avg if d else "",
                    "hrv_status": d.hrv_status if d else "",
                    "steps": d.steps if d else "",
                    "steps_7d_avg": d.steps_7day_avg if d else "",
                    "directory": a.directory,
                }
            )

        # JSON Index
        json_path = output_dir / "activities_index.json"
        json_path.write_text(json.dumps(index_data, indent=2, ensure_ascii=False))

        # CSV Index
        if index_data:
            csv_path = output_dir / "activities_index.csv"
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(index_data[0].keys()))
                writer.writeheader()
                writer.writerows(index_data)
