"""Fetch and aggregate daily health statistics and 7-day averages from Garmin Connect."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from dateutil import parser as date_parser
from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
)

from garmin_analyzer.models import DailyHealthSummary

logger = logging.getLogger(__name__)


def parse_date_input(target_date: str | datetime | None = None) -> tuple[str, datetime]:
    """Flexibly parses user-provided date representations into a (YYYY-MM-DD, datetime) tuple.

    Supports:
    - None / 'today' / 'now' -> current date
    - 'yesterday' -> previous date
    - German/European format: '16.09.2026', '16/09/2026', '16-09-2026'
    - ISO formats: '2026-09-16', '2026.09.16', '2026/09/16'
    - General natural dates supported by dateutil.parser
    """
    if target_date is None:
        now = datetime.now(UTC)
        return now.strftime("%Y-%m-%d"), now

    if isinstance(target_date, datetime):
        dt = target_date if target_date.tzinfo else target_date.replace(tzinfo=UTC)
        return dt.strftime("%Y-%m-%d"), dt

    cleaned = str(target_date).strip()
    lower = cleaned.lower()
    if lower in ("today", "now"):
        now = datetime.now(UTC)
        return now.strftime("%Y-%m-%d"), now
    if lower == "yesterday":
        yest = datetime.now(UTC) - timedelta(days=1)
        return yest.strftime("%Y-%m-%d"), yest

    try:
        import re

        parts = re.split(r"[-./\s]", cleaned)
        year_first = len(parts[0]) == 4 if parts else False
        dt = date_parser.parse(cleaned, yearfirst=year_first, dayfirst=not year_first)
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=UTC)
        return dt.strftime("%Y-%m-%d"), dt
    except Exception as err:
        raise ValueError(
            f"Could not parse date '{target_date}'. Expected formats like 'YYYY-MM-DD', 'DD.MM.YYYY', or 'today'."
        ) from err


def fetch_daily_health(
    client: Garmin,
    target_date: str | datetime | None = None,
) -> tuple[DailyHealthSummary, dict[str, Any]]:
    """Fetches all health metrics for a target date plus 7-day averages.

    Target date can be 'YYYY-MM-DD', 'DD.MM.YYYY', 'today', 'yesterday', or a datetime object.
    """
    date_str, dt = parse_date_input(target_date)

    # Start date for 7-day range (6 days prior + target day = 7 days)
    start_7d = dt - timedelta(days=6)
    start_7d_str = start_7d.strftime("%Y-%m-%d")

    raw_data: dict[str, Any] = {"date": date_str}
    summary = DailyHealthSummary(date=date_str)

    # 1. User Daily Summary
    try:
        user_summary = client.get_user_summary(date_str)
        raw_data["user_summary"] = user_summary
        if isinstance(user_summary, dict):
            summary.steps = user_summary.get("totalSteps")
            summary.steps_goal = user_summary.get("dailyStepGoal")
            summary.floors_ascended = user_summary.get("floorsAscended")
            summary.resting_hr = user_summary.get("restingHeartRate") or user_summary.get(
                "currentRestingHeartRate"
            )
            summary.min_hr = user_summary.get("minHeartRate")
            summary.max_hr = user_summary.get("maxHeartRate")
            summary.stress_avg = user_summary.get("averageStressLevel")
    except (GarminConnectConnectionError, GarminConnectAuthenticationError, OSError) as e:
        logger.debug("Failed to fetch user summary for %s: %s", date_str, e)

    # 2. Heart Rate & Resting Heart Rate Details
    try:
        hr_data = client.get_heart_rates(date_str)
        raw_data["heart_rates"] = hr_data
        if isinstance(hr_data, dict):
            if summary.resting_hr is None:
                summary.resting_hr = hr_data.get("restingHeartRate")
            if summary.min_hr is None:
                summary.min_hr = hr_data.get("minHeartRate")
            if summary.max_hr is None:
                summary.max_hr = hr_data.get("maxHeartRate")
            if hr_data.get("lastSevenDaysAvgRestingHeartRate") is not None:
                summary.rhr_7day_avg = float(hr_data["lastSevenDaysAvgRestingHeartRate"])
    except (GarminConnectConnectionError, GarminConnectAuthenticationError, OSError) as e:
        logger.debug("Failed to fetch heart rates for %s: %s", date_str, e)

    # 3. 7-Day Resting Heart Rate Trend
    try:
        rhr_data = client.get_rhr_day(date_str)
        raw_data["rhr_day"] = rhr_data
        if isinstance(rhr_data, dict) and summary.rhr_7day_avg is None:
            # Garmin often provides 7-day average resting HR
            rhr_7d = (
                rhr_data.get("wellnessSevenDayAvgRestingHeartRate")
                or rhr_data.get("sevenDayAvgRestingHeartRate")
                or rhr_data.get("statistics", {}).get("sevenDayAverage")
            )
            if rhr_7d is not None:
                summary.rhr_7day_avg = float(rhr_7d)
    except (GarminConnectConnectionError, GarminConnectAuthenticationError, OSError) as e:
        logger.debug("Failed to fetch RHR day data for %s: %s", date_str, e)

    # 4. HRV (Heart Rate Variability / HFV)
    try:
        hrv_data = client.get_hrv_data(date_str)
        raw_data["hrv"] = hrv_data
        if isinstance(hrv_data, dict):
            hrv_summary = hrv_data.get("hrvSummary") or {}
            summary.hrv_last_night_avg = hrv_summary.get("lastNightAvg")
            summary.hrv_7day_avg = hrv_summary.get("weeklyAvg")
            summary.hrv_status = hrv_summary.get("status")

            baseline = hrv_summary.get("baseline") or {}
            summary.hrv_baseline_low = baseline.get("balancedLow") or baseline.get("lowUpper")
            summary.hrv_baseline_high = baseline.get("balancedUpper")
    except (GarminConnectConnectionError, GarminConnectAuthenticationError, OSError) as e:
        logger.debug("Failed to fetch HRV data for %s: %s", date_str, e)

    # 5. Steps & 7-Day Steps Average
    try:
        daily_steps = client.get_daily_steps(start_7d_str, date_str)
        raw_data["steps_7d_history"] = daily_steps
        if isinstance(daily_steps, list) and len(daily_steps) > 0:
            step_counts = [
                item.get("totalSteps", 0) for item in daily_steps if isinstance(item, dict)
            ]
            if step_counts:
                summary.steps_7day_avg = round(sum(step_counts) / len(step_counts), 1)
                # If target day steps not yet set, get from the matching day
                if summary.steps is None:
                    target_entry = next(
                        (x for x in daily_steps if x.get("calendarDate") == date_str),
                        daily_steps[-1],
                    )
                    summary.steps = target_entry.get("totalSteps")
                    summary.steps_goal = target_entry.get("stepGoal")
    except (GarminConnectConnectionError, GarminConnectAuthenticationError, OSError) as e:
        logger.debug("Failed to fetch daily steps for %s: %s", date_str, e)

    # 6. Sleep Data
    try:
        sleep_data = client.get_sleep_data(date_str)
        raw_data["sleep"] = sleep_data
        if isinstance(sleep_data, dict):
            sleep_dto = sleep_data.get("dailySleepDTO") or {}
            summary.sleep_seconds = sleep_dto.get("sleepTimeSeconds")
            summary.sleep_deep_seconds = sleep_dto.get("deepSleepSeconds")
            summary.sleep_light_seconds = sleep_dto.get("lightSleepSeconds")
            summary.sleep_rem_seconds = sleep_dto.get("remSleepSeconds")
            summary.sleep_awake_seconds = sleep_dto.get("awakeSleepSeconds")

            scores = sleep_dto.get("sleepScores") or {}
            overall = scores.get("overall") or {}
            summary.sleep_score = overall.get("value")
    except (GarminConnectConnectionError, GarminConnectAuthenticationError, OSError) as e:
        logger.debug("Failed to fetch sleep data for %s: %s", date_str, e)

    # 7. Stress & Body Battery
    try:
        stress_data = client.get_stress_data(date_str)
        raw_data["stress"] = stress_data
        if isinstance(stress_data, dict) and summary.stress_avg is None:
            summary.stress_avg = stress_data.get("avgStressLevel")
    except (GarminConnectConnectionError, GarminConnectAuthenticationError, OSError) as e:
        logger.debug("Failed to fetch stress data for %s: %s", date_str, e)

    try:
        bb_data = client.get_body_battery(date_str)
        raw_data["body_battery"] = bb_data
        if isinstance(bb_data, list) and len(bb_data) > 0:
            # Body battery list contains event entries
            first_entry = bb_data[0]
            if isinstance(first_entry, dict):
                summary.body_battery_charged = first_entry.get("charged")
                summary.body_battery_drained = first_entry.get("drained")
                recent = first_entry.get("bodyBatteryMostRecentValue")
                if recent is None:
                    bb_vals = first_entry.get("bodyBatteryValuesArray") or []
                    if bb_vals and len(bb_vals[-1]) > 1:
                        recent = bb_vals[-1][1]
                summary.body_battery_most_recent = recent
    except (GarminConnectConnectionError, GarminConnectAuthenticationError, OSError) as e:
        logger.debug("Failed to fetch body battery for %s: %s", date_str, e)

    # 8. Training Readiness & Status
    try:
        readiness = client.get_training_readiness(date_str)
        raw_data["training_readiness"] = readiness
        if isinstance(readiness, dict):
            summary.training_readiness_score = readiness.get("score")
    except (GarminConnectConnectionError, GarminConnectAuthenticationError, OSError) as e:
        logger.debug("Failed to fetch training readiness for %s: %s", date_str, e)

    try:
        status_data = client.get_training_status(date_str)
        raw_data["training_status"] = status_data
        if isinstance(status_data, dict):
            summary.training_status = status_data.get(
                "trainingStatusFeedbackPhrase"
            ) or status_data.get("status")
    except (GarminConnectConnectionError, GarminConnectAuthenticationError, OSError) as e:
        logger.debug("Failed to fetch training status for %s: %s", date_str, e)

    summary.raw_data = raw_data
    return summary, raw_data
