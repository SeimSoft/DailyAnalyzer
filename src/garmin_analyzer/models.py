"""Pydantic data models for Garmin activities, telemetry, daily health stats, and photos."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class PhotoInfo(BaseModel):
    """Metadata for an image/photo attached to an activity."""

    photo_id: str
    url: str
    title: str | None = None
    date_taken: str | None = None
    local_path: str | None = None
    size_bytes: int | None = None
    source: str = "activity"


class LocationInfo(BaseModel):
    """Geographical location information of the activity."""

    start_latitude: float | None = None
    start_longitude: float | None = None
    end_latitude: float | None = None
    end_longitude: float | None = None
    min_elevation_meters: float | None = None
    max_elevation_meters: float | None = None
    location_name: str | None = None
    course_id: str | None = None

    @property
    def has_coordinates(self) -> bool:
        return self.start_latitude is not None and self.start_longitude is not None


class PerformanceStats(BaseModel):
    """Comprehensive performance telemetry and statistics."""

    distance_meters: float = 0.0
    duration_seconds: float = 0.0
    elapsed_seconds: float | None = None
    moving_duration_seconds: float | None = None

    calories: int | None = None
    average_hr: int | None = None
    max_hr: int | None = None

    avg_speed_mps: float | None = None
    max_speed_mps: float | None = None

    elevation_gain_meters: float | None = None
    elevation_loss_meters: float | None = None

    avg_cadence: float | None = None
    max_cadence: float | None = None

    avg_power: float | None = None
    max_power: float | None = None
    normalized_power: float | None = None

    vo2_max: float | None = None
    aerobic_training_effect: float | None = None
    anaerobic_training_effect: float | None = None
    avg_temperature_c: float | None = None

    @field_validator("calories", "average_hr", "max_hr", mode="before")
    @classmethod
    def _round_int(cls, v: Any) -> int | None:
        if v is None:
            return None
        try:
            return int(round(float(v)))
        except (ValueError, TypeError):
            return None

    @property
    def distance_km(self) -> float:
        return round(self.distance_meters / 1000.0, 2)

    @property
    def distance_miles(self) -> float:
        return round(self.distance_meters * 0.000621371, 2)

    @property
    def avg_speed_kmh(self) -> float | None:
        if self.avg_speed_mps is not None:
            return round(self.avg_speed_mps * 3.6, 2)
        if self.duration_seconds > 0 and self.distance_meters > 0:
            return round((self.distance_meters / self.duration_seconds) * 3.6, 2)
        return None

    @property
    def max_speed_kmh(self) -> float | None:
        if self.max_speed_mps is not None:
            return round(self.max_speed_mps * 3.6, 2)
        return None

    @property
    def avg_pace_min_per_km(self) -> str | None:
        """Calculates pace as MM:SS per km."""
        speed_kmh = self.avg_speed_kmh
        if speed_kmh and speed_kmh > 0:
            seconds_per_km = 3600.0 / speed_kmh
            mins = int(seconds_per_km // 60)
            secs = int(seconds_per_km % 60)
            return f"{mins:02d}:{secs:02d} /km"
        return None

    @property
    def duration_formatted(self) -> str:
        """Formats duration as HH:MM:SS or MM:SS."""
        total_secs = int(self.duration_seconds)
        hours = total_secs // 3600
        mins = (total_secs % 3600) // 60
        secs = total_secs % 60
        if hours > 0:
            return f"{hours:02d}:{mins:02d}:{secs:02d}"
        return f"{mins:02d}:{secs:02d}"


class SplitInfo(BaseModel):
    """Lap or split section data."""

    split_index: int
    distance_meters: float = 0.0
    duration_seconds: float = 0.0
    avg_speed_mps: float | None = None
    avg_hr: int | None = None
    max_hr: int | None = None
    elevation_gain_meters: float | None = None
    elevation_loss_meters: float | None = None
    calories: int | None = None

    @field_validator("avg_hr", "max_hr", "calories", mode="before")
    @classmethod
    def _round_int(cls, v: Any) -> int | None:
        if v is None:
            return None
        try:
            return int(round(float(v)))
        except (ValueError, TypeError):
            return None


class WeatherInfo(BaseModel):
    """Weather condition captured during the activity."""

    temperature_c: float | None = None
    relative_humidity: float | None = None
    wind_speed_mps: float | None = None
    wind_direction_compass: str | None = None
    weather_condition: str | None = None
    issue_time: str | None = None


class ActivityOverview(BaseModel):
    """Curated overview answering 'what have I done', 'where was I', and 'all stats'."""

    activity_id: int
    activity_name: str
    activity_type: str
    activity_type_key: str | None = None
    activity_sub_sport: str | None = None
    description: str | None = None
    event_type: str | None = None

    start_time_local: str
    start_time_gmt: str | None = None

    location: LocationInfo = Field(default_factory=LocationInfo)
    stats: PerformanceStats = Field(default_factory=PerformanceStats)
    splits: list[SplitInfo] = Field(default_factory=list)
    weather: WeatherInfo | None = None
    hr_zones: list[dict[str, Any]] | dict[str, Any] | None = None
    photos_count: int = 0

    @property
    def date_str(self) -> str:
        """Returns YYYY-MM-DD date extracted from start_time_local."""
        try:
            return self.start_time_local.split(" ")[0].split("T")[0]
        except (IndexError, AttributeError):
            return datetime.now(UTC).strftime("%Y-%m-%d")


class DailyHealthSummary(BaseModel):
    """General health metrics for a day and preceding 7-day averages."""

    date: str

    # Heart Rate & 7-day average
    resting_hr: int | None = None
    min_hr: int | None = None
    max_hr: int | None = None
    rhr_7day_avg: float | None = None

    # HRV (Heart Rate Variability / HFV)
    hrv_last_night_avg: float | None = None
    hrv_7day_avg: float | None = None
    hrv_status: str | None = None
    hrv_baseline_low: float | None = None
    hrv_baseline_high: float | None = None

    # Steps & 7-day average
    steps: int | None = None
    steps_goal: int | None = None
    steps_7day_avg: float | None = None
    floors_ascended: float | int | None = None

    # Sleep & Recovery
    sleep_seconds: int | None = None
    sleep_score: int | None = None
    sleep_deep_seconds: int | None = None
    sleep_light_seconds: int | None = None
    sleep_rem_seconds: int | None = None
    sleep_awake_seconds: int | None = None

    # Stress & Body Battery
    stress_avg: int | None = None
    body_battery_charged: int | None = None
    body_battery_drained: int | None = None
    body_battery_most_recent: int | None = None

    # Training readiness / status
    training_readiness_score: int | None = None
    training_status: str | None = None

    # Activities that occurred on this day
    activities: list[ActivityOverview] = Field(default_factory=list)

    # Raw metrics dictionary for complete data retention
    raw_data: dict[str, Any] | None = None

    @property
    def sleep_duration_formatted(self) -> str | None:
        if self.sleep_seconds is None:
            return None
        hours = self.sleep_seconds // 3600
        mins = (self.sleep_seconds % 3600) // 60
        return f"{hours}h {mins}m"


class DownloadedActivity(BaseModel):
    """Complete bundle of downloaded activity data, tracks, photos, and daily context."""

    overview: ActivityOverview
    directory: str
    track_gpx_path: str | None = None
    track_tcx_path: str | None = None
    track_fit_path: str | None = None
    photos: list[PhotoInfo] = Field(default_factory=list)
    daily_health: DailyHealthSummary | None = None
    files_saved: list[str] = Field(default_factory=list)
