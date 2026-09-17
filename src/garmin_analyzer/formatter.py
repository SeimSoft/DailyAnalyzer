"""Markdown and Rich terminal formatters for Garmin activities and health stats."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from garmin_analyzer.models import (
    ActivityOverview,
    DailyHealthSummary,
    DownloadedActivity,
)


def format_activity_markdown(activity: DownloadedActivity) -> str:
    """Generates a comprehensive, human-readable markdown report for an activity."""
    overview = activity.overview
    stats = overview.stats
    loc = overview.location
    daily = activity.daily_health

    lines: list[str] = [
        f"# {overview.activity_name}",
        "",
        f"> **Activity ID**: `{overview.activity_id}` | **Date**: {overview.start_time_local} | **Type**: {overview.activity_type.capitalize()}",
        "",
        "## 🏃 What Have I Done",
        "",
        f"- **Activity Type**: {overview.activity_type.replace('_', ' ').title()}",
    ]

    if overview.activity_sub_sport:
        lines.append(f"- **Sub-Sport**: {overview.activity_sub_sport.replace('_', ' ').title()}")
    if overview.description:
        lines.append(f"- **Description**: {overview.description}")
    if overview.event_type:
        lines.append(f"- **Event Type**: {overview.event_type.replace('_', ' ').title()}")

    lines.extend(
        [
            f"- **Start Time (Local)**: {overview.start_time_local}",
            f"- **Start Time (GMT)**: {overview.start_time_gmt or 'N/A'}",
            f"- **Duration**: {stats.duration_formatted}",
        ]
    )

    if stats.moving_duration_seconds:
        moving_mins = int(stats.moving_duration_seconds // 60)
        moving_secs = int(stats.moving_duration_seconds % 60)
        lines.append(f"- **Moving Duration**: {moving_mins:02d}:{moving_secs:02d}")

    # Where was I
    lines.extend(
        [
            "",
            "## 📍 Where Was I",
            "",
        ]
    )

    if loc.has_coordinates:
        lines.extend(
            [
                (
                    f"- **Start Coordinates**: `{loc.start_latitude:.5f}, {loc.start_longitude:.5f}` "
                    f"([OpenStreetMap](https://www.openstreetmap.org/?mlat={loc.start_latitude}&mlon={loc.start_longitude}#map=15/{loc.start_latitude}/{loc.start_longitude}))"
                ),
                f"- **End Coordinates**: `{loc.end_latitude:.5f}, {loc.end_longitude:.5f}`"
                if loc.end_latitude and loc.end_longitude
                else "",
            ]
        )
    else:
        lines.append("- **GPS Coordinates**: Not recorded or indoor activity")

    if loc.location_name:
        lines.append(f"- **Location Name**: {loc.location_name}")
    if loc.min_elevation_meters is not None and loc.max_elevation_meters is not None:
        lines.append(
            f"- **Elevation Range**: {loc.min_elevation_meters:.0f}m - {loc.max_elevation_meters:.0f}m"
        )

    # Track Files
    track_links = []
    if activity.track_gpx_path:
        track_links.append("`track.gpx` (GPX format)")
    if activity.track_tcx_path:
        track_links.append("`track.tcx` (TCX format)")
    if activity.track_fit_path:
        track_links.append("`track.fit` (Original FIT sensor data)")

    if track_links:
        lines.append(f"- **Downloaded GPS Tracks**: {', '.join(track_links)}")

    # All Stats
    lines.extend(
        [
            "",
            "## 📊 All Performance Statistics",
            "",
            "| Metric | Value |",
            "| :--- | :--- |",
            f"| **Distance** | **{stats.distance_km} km** ({stats.distance_miles} miles) |",
            f"| **Duration** | {stats.duration_formatted} |",
            f"| **Average Pace** | {stats.avg_pace_min_per_km or 'N/A'} |",
            f"| **Average Speed** | {stats.avg_speed_kmh or 'N/A'} km/h |",
            f"| **Max Speed** | {stats.max_speed_kmh or 'N/A'} km/h |",
            f"| **Average Heart Rate** | {stats.average_hr or 'N/A'} bpm |",
            f"| **Max Heart Rate** | {stats.max_hr or 'N/A'} bpm |",
            f"| **Calories Burned** | {stats.calories or 'N/A'} kcal |",
            f"| **Elevation Gain** | +{stats.elevation_gain_meters:.0f}m |"
            if stats.elevation_gain_meters is not None
            else "| **Elevation Gain** | N/A |",
            f"| **Elevation Loss** | -{stats.elevation_loss_meters:.0f}m |"
            if stats.elevation_loss_meters is not None
            else "| **Elevation Loss** | N/A |",
            f"| **Average Cadence** | {stats.avg_cadence or 'N/A'} rpm |",
            f"| **Max Cadence** | {stats.max_cadence or 'N/A'} rpm |",
            f"| **Average Power** | {stats.avg_power or 'N/A'} W |",
            f"| **Max Power** | {stats.max_power or 'N/A'} W |",
            f"| **Normalized Power** | {stats.normalized_power or 'N/A'} W |",
            f"| **Aerobic Training Effect** | {stats.aerobic_training_effect or 'N/A'} |",
            f"| **Anaerobic Training Effect** | {stats.anaerobic_training_effect or 'N/A'} |",
            f"| **VO2 Max Estimate** | {stats.vo2_max or 'N/A'} |",
        ]
    )

    # Weather
    if overview.weather:
        w = overview.weather
        lines.extend(
            [
                "",
                "## 🌤️ Weather Conditions",
                "",
                f"- **Temperature**: {w.temperature_c:.1f}°C"
                if w.temperature_c is not None
                else "- **Temperature**: N/A",
                f"- **Condition**: {w.weather_condition or 'N/A'}",
                f"- **Humidity**: {w.relative_humidity}%"
                if w.relative_humidity is not None
                else "- **Humidity**: N/A",
                f"- **Wind**: {w.wind_speed_mps} m/s ({w.wind_direction_compass or 'N/A'})"
                if w.wind_speed_mps is not None
                else "- **Wind**: N/A",
            ]
        )

    # Splits
    if overview.splits:
        lines.extend(
            [
                "",
                "## ⏱️ Splits & Laps",
                "",
                "| Split | Distance | Time | Avg Pace | Avg HR | Max HR | Elev Gain |",
                "| :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
            ]
        )
        for s in overview.splits:
            dist_km = s.distance_meters / 1000.0
            total_s = int(s.duration_seconds)
            mins = total_s // 60
            secs = total_s % 60
            time_str = f"{mins:02d}:{secs:02d}"
            pace_str = "N/A"
            if dist_km > 0 and total_s > 0:
                sec_km = total_s / dist_km
                pace_str = f"{int(sec_km // 60):02d}:{int(sec_km % 60):02d} /km"
            elev_str = (
                f"+{s.elevation_gain_meters:.0f}m" if s.elevation_gain_meters is not None else "-"
            )
            lines.append(
                f"| {s.split_index} | {dist_km:.2f} km | {time_str} | {pace_str} | {s.avg_hr or '-'} | {s.max_hr or '-'} | {elev_str} |"
            )

    # Daily Health Context
    if daily:
        lines.extend(
            [
                "",
                f"## 💓 Daily Health Context for {daily.date}",
                "",
                "| Metric | Today's Value | 7-Day Average / Baseline |",
                "| :--- | :--- | :--- |",
                f"| **Resting Heart Rate** | {daily.resting_hr or 'N/A'} bpm | {f'{daily.rhr_7day_avg:.1f} bpm' if daily.rhr_7day_avg else 'N/A'} |",
                f"| **HRV (Heart Rate Variability)** | {f'{daily.hrv_last_night_avg:.0f} ms' if daily.hrv_last_night_avg else 'N/A'} ({daily.hrv_status or 'N/A'}) | {f'{daily.hrv_7day_avg:.0f} ms' if daily.hrv_7day_avg else 'N/A'} |",
                f"| **Steps** | {f'{daily.steps:,}' if daily.steps else 'N/A'} (Goal: {f'{daily.steps_goal:,}' if daily.steps_goal else 'N/A'}) | {f'{daily.steps_7day_avg:,.0f} steps/day' if daily.steps_7day_avg else 'N/A'} |",
                f"| **Sleep Duration & Score** | {daily.sleep_duration_formatted or 'N/A'} (Score: {daily.sleep_score or 'N/A'}) | - |",
                f"| **Average Stress Level** | {daily.stress_avg or 'N/A'} / 100 | - |",
                f"| **Body Battery** | Charged: +{daily.body_battery_charged or 0}, Drained: -{daily.body_battery_drained or 0} | - |",
                f"| **Training Readiness** | {daily.training_readiness_score or 'N/A'} / 100 | {daily.training_status or 'N/A'} |",
            ]
        )

    # Uploaded Photos
    lines.extend(
        [
            "",
            "## 📸 Uploaded Photos & Images",
            "",
        ]
    )
    if activity.photos:
        lines.append(f"Found **{len(activity.photos)}** photo(s) attached to this activity:\n")
        for idx, p in enumerate(activity.photos, 1):
            title = p.title or f"Photo {idx}"
            local = f"`photos/{p.local_path.split('/')[-1]}`" if p.local_path else "Not downloaded"
            date = f" ({p.date_taken})" if p.date_taken else ""
            lines.append(f"- **{title}**{date}: {local}")
    else:
        lines.append("- *No uploaded photos found for this activity.*")

    lines.append("")
    return "\n".join(lines)


def format_daily_markdown(daily: DailyHealthSummary) -> str:
    """Generates a standalone daily health & 7-day trend markdown report."""
    lines = [
        f"# Daily Health & 7-Day Stats: {daily.date}",
        "",
        "## 💓 Heart Rate & Trends",
        f"- **Resting Heart Rate**: **{daily.resting_hr or 'N/A'} bpm**",
        f"- **7-Day Average Resting HR**: **{f'{daily.rhr_7day_avg:.1f} bpm' if daily.rhr_7day_avg else 'N/A'}**",
        f"- **Day Min / Max Heart Rate**: {daily.min_hr or 'N/A'} / {daily.max_hr or 'N/A'} bpm",
        "",
        "## 📈 HRV (Heart Rate Variability / HFV)",
        f"- **Last Night Average HRV**: **{f'{daily.hrv_last_night_avg:.0f} ms' if daily.hrv_last_night_avg else 'N/A'}**",
        f"- **7-Day Average HRV**: **{f'{daily.hrv_7day_avg:.0f} ms' if daily.hrv_7day_avg else 'N/A'}**",
        f"- **HRV Status**: **{daily.hrv_status or 'N/A'}**",
    ]

    if daily.hrv_baseline_low and daily.hrv_baseline_high:
        lines.append(
            f"- **HRV Baseline Range**: {daily.hrv_baseline_low:.0f} ms - {daily.hrv_baseline_high:.0f} ms"
        )

    lines.extend(
        [
            "",
            "## 👣 Steps & Activity",
            f"- **Total Steps**: **{f'{daily.steps:,}' if daily.steps else 'N/A'}**",
            f"- **Step Goal**: {f'{daily.steps_goal:,}' if daily.steps_goal else 'N/A'}",
            f"- **7-Day Average Steps**: **{f'{daily.steps_7day_avg:,.0f} steps/day' if daily.steps_7day_avg else 'N/A'}**",
            f"- **Floors Ascended**: {daily.floors_ascended or 'N/A'}",
            "",
            "## 😴 Sleep & Recovery",
            f"- **Total Sleep**: **{daily.sleep_duration_formatted or 'N/A'}**",
            f"- **Sleep Score**: **{daily.sleep_score or 'N/A'} / 100**",
        ]
    )

    if daily.sleep_deep_seconds or daily.sleep_rem_seconds:
        deep_m = (daily.sleep_deep_seconds or 0) // 60
        light_m = (daily.sleep_light_seconds or 0) // 60
        rem_m = (daily.sleep_rem_seconds or 0) // 60
        awake_m = (daily.sleep_awake_seconds or 0) // 60
        lines.append(
            f"- **Stages**: Deep: {deep_m}m | Light: {light_m}m | REM: {rem_m}m | Awake: {awake_m}m"
        )

    lines.extend(
        [
            "",
            "## ⚡ Stress & Body Battery",
            f"- **Average Stress Level**: **{daily.stress_avg or 'N/A'} / 100**",
            f"- **Body Battery Charged**: +{daily.body_battery_charged or 0}",
            f"- **Body Battery Drained**: -{daily.body_battery_drained or 0}",
            f"- **Body Battery Most Recent**: {daily.body_battery_most_recent or 'N/A'}",
            "",
            "## 🎯 Training Status & Readiness",
            f"- **Training Readiness**: **{daily.training_readiness_score or 'N/A'} / 100**",
            f"- **Training Status**: **{daily.training_status or 'N/A'}**",
            "",
        ]
    )

    if daily.activities:
        lines.extend(
            [
                f"## 🏃 Activities on This Day ({len(daily.activities)})",
                "",
            ]
        )
        for act in daily.activities:
            stats = act.stats
            dur = stats.duration_formatted or "N/A"
            dist = f"{stats.distance_km:.2f} km" if stats.distance_km else "N/A"
            pace = f" • Pace: {stats.avg_pace_min_per_km}" if stats.avg_pace_min_per_km else ""
            hr = f" • Avg HR: {stats.average_hr} bpm" if stats.average_hr else ""
            cals = f" • {stats.calories} kcal" if stats.calories else ""
            elev = (
                f" • Gain: +{stats.elevation_gain_meters:.0f}m"
                if stats.elevation_gain_meters is not None
                else ""
            )
            time_part = (
                act.start_time_local.split(" ")[-1]
                if " " in act.start_time_local
                else act.start_time_local
            )

            lines.append(
                f"- **{act.activity_name}** (`{act.activity_type.capitalize()}` at {time_part})"
            )
            lines.append(
                f"  - ID: `{act.activity_id}` • Distance: {dist} • Duration: {dur}{pace}{hr}{cals}{elev}"
            )
        lines.append("")

    return "\n".join(lines)


def print_activity_summary(activity: DownloadedActivity, console: Console) -> None:
    """Prints a styled Rich summary of an activity to the terminal."""
    overview = activity.overview
    stats = overview.stats
    loc = overview.location
    daily = activity.daily_health

    title = (
        f"[bold cyan]{overview.activity_name}[/bold cyan] ({overview.activity_type.capitalize()})"
    )
    subtitle = f"{overview.start_time_local} • ID: {overview.activity_id}"

    table = Table(title="Performance Stats", show_header=True, header_style="bold magenta")
    table.add_column("Metric", style="dim")
    table.add_column("Value", style="bold")

    table.add_row("Distance", f"{stats.distance_km} km ({stats.distance_miles} mi)")
    table.add_row("Duration", stats.duration_formatted)
    if stats.avg_pace_min_per_km:
        table.add_row("Avg Pace", stats.avg_pace_min_per_km)
    if stats.avg_speed_kmh:
        table.add_row("Avg Speed", f"{stats.avg_speed_kmh} km/h")
    if stats.average_hr:
        table.add_row("Avg / Max HR", f"{stats.average_hr} / {stats.max_hr or '-'} bpm")
    if stats.calories:
        table.add_row("Calories", f"{stats.calories} kcal")
    if stats.elevation_gain_meters is not None:
        table.add_row("Elevation Gain", f"+{stats.elevation_gain_meters:.0f} m")

    if loc.has_coordinates:
        table.add_row("GPS Start", f"{loc.start_latitude:.4f}, {loc.start_longitude:.4f}")

    if activity.photos:
        table.add_row("Photos", f"[green]{len(activity.photos)} uploaded photo(s)[/green]")

    panel_content = table
    console.print(Panel(panel_content, title=title, subtitle=subtitle, expand=False))

    if daily:
        print_daily_summary(daily, console)


def print_daily_summary(daily: DailyHealthSummary, console: Console) -> None:
    """Prints a styled Rich table of daily health and 7-day averages to the terminal."""
    table = Table(
        title=f"💓 Daily Health & 7-Day Trends ({daily.date})",
        show_header=True,
        header_style="bold green",
    )
    table.add_column("Health Metric", style="dim")
    table.add_column("Today", style="bold")
    table.add_column("7-Day Avg / Trend", style="cyan")

    table.add_row(
        "Resting Heart Rate",
        f"{daily.resting_hr} bpm" if daily.resting_hr else "N/A",
        f"{daily.rhr_7day_avg:.1f} bpm" if daily.rhr_7day_avg else "N/A",
    )
    table.add_row(
        "HRV Index (HFV)",
        f"{daily.hrv_last_night_avg:.0f} ms ({daily.hrv_status or '-'})"
        if daily.hrv_last_night_avg
        else "N/A",
        f"{daily.hrv_7day_avg:.0f} ms" if daily.hrv_7day_avg else "N/A",
    )
    table.add_row(
        "Steps",
        f"{daily.steps:,}" if daily.steps else "N/A",
        f"{daily.steps_7day_avg:,.0f} steps/day" if daily.steps_7day_avg else "N/A",
    )
    table.add_row(
        "Sleep & Score",
        f"{daily.sleep_duration_formatted or 'N/A'} (Score: {daily.sleep_score or '-'})",
        "-",
    )
    table.add_row("Avg Stress", f"{daily.stress_avg} / 100" if daily.stress_avg else "N/A", "-")
    table.add_row(
        "Body Battery",
        f"+{daily.body_battery_charged or 0} / -{daily.body_battery_drained or 0}",
        "-",
    )
    if daily.training_readiness_score or daily.training_status:
        table.add_row(
            "Training Readiness",
            f"{daily.training_readiness_score or '-'} / 100",
            daily.training_status or "-",
        )

    console.print(table)


def print_activities_table(
    activities: list[ActivityOverview],
    console: Console,
    title: str | None = None,
    show_photos: bool = False,
) -> None:
    """Prints a tabular listing of multiple activities."""
    has_photos = show_photos or any(act.photos_count > 0 for act in activities)
    table = Table(
        title=title or f"Recent Garmin Activities ({len(activities)})",
        show_header=True,
        header_style="bold blue",
    )
    table.add_column("ID", style="dim")
    table.add_column("Date", style="cyan")
    table.add_column("Type", style="bold")
    table.add_column("Name")
    table.add_column("Distance", justify="right")
    table.add_column("Duration", justify="right")
    table.add_column("Avg HR", justify="right")
    if has_photos:
        table.add_column("Photos", justify="right", style="magenta")

    for act in activities:
        row = [
            str(act.activity_id),
            act.date_str,
            act.activity_type.capitalize(),
            act.activity_name[:30],
            f"{act.stats.distance_km} km",
            act.stats.duration_formatted,
            f"{act.stats.average_hr} bpm" if act.stats.average_hr else "-",
        ]
        if has_photos:
            row.append(f"📸 {act.photos_count}" if act.photos_count > 0 else "-")
        table.add_row(*row)

    console.print(table)
