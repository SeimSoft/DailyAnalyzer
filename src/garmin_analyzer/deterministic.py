"""Deterministic report and narrative generator using heuristics (no LLM, 0 API tokens)."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any

from garmin_analyzer.elevation_profile import extract_elevation_points
from garmin_analyzer.storyteller import assemble_self_contained_diary

logger = logging.getLogger(__name__)

# German weekday and month names
GERMAN_WEEKDAYS = [
    "Montag",
    "Dienstag",
    "Mittwoch",
    "Donnerstag",
    "Freitag",
    "Samstag",
    "Sonntag",
]

GERMAN_MONTHS = [
    "Januar",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
]

SPORT_CONFIG = {
    "hiking": {"name": "Wanderung", "verb": "wandern", "emoji": "🥾"},
    "walking": {"name": "Spaziergang", "verb": "spazieren", "emoji": "🚶"},
    "running": {"name": "Lauf", "verb": "laufen", "emoji": "🏃"},
    "trail_running": {"name": "Trailrun", "verb": "laufen", "emoji": "🏔️"},
    "cycling": {"name": "Radausfahrt", "verb": "radfahren", "emoji": "🚴"},
    "road_biking": {"name": "Rennradtour", "verb": "radfahren", "emoji": "🚴"},
    "gravel_cycling": {"name": "Gravel-Tour", "verb": "radfahren", "emoji": "🚴"},
    "mountain_biking": {"name": "Mountainbike-Tour", "verb": "biken", "emoji": "🚵"},
    "swimming": {"name": "Schwimmeinheit", "verb": "schwimmen", "emoji": "🏊"},
    "skiing": {"name": "Skitour", "verb": "skifahren", "emoji": "🎿"},
    "backcountry_skiing": {"name": "Skitour", "verb": "skifahren", "emoji": "🎿"},
    "climbing": {"name": "Klettertour", "verb": "klettern", "emoji": "🧗"},
    "mountaineering": {"name": "Bergtour", "verb": "bergsteigen", "emoji": "🧗"},
    "fitness_equipment": {"name": "Workout", "verb": "trainieren", "emoji": "🏋️"},
}


def format_german_date(date_str: str) -> str:
    """Formats an ISO date string (YYYY-MM-DD) into a German date string."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d").date()
        wday = GERMAN_WEEKDAYS[dt.weekday()]
        month = GERMAN_MONTHS[dt.month - 1]
        return f"{wday}, {dt.day}. {month} {dt.year}"
    except (ValueError, IndexError):
        return date_str


def _format_duration(seconds: float | None) -> str:
    """Formats duration in seconds to hh:mm:ss or mm:ss."""
    if not seconds:
        return "00:00"
    total_sec = int(seconds)
    hours = total_sec // 3600
    minutes = (total_sec % 3600) // 60
    secs = total_sec % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d} h"
    return f"{minutes:02d}:{secs:02d} min"


def _format_pace_or_speed(sport_type: str, dist_km: float | None, duration_s: float | None) -> str:
    """Calculates pace (min/km) for running/hiking/walking, or speed (km/h) for cycling."""
    if not dist_km or dist_km <= 0 or not duration_s or duration_s <= 0:
        return "-"

    sport = (sport_type or "").lower()
    if any(k in sport for k in ("cycl", "bike")):
        speed_kmh = dist_km / (duration_s / 3600.0)
        return f"{speed_kmh:.1f} km/h"

    # Pace min/km
    sec_per_km = duration_s / dist_km
    p_min = int(sec_per_km // 60)
    p_sec = int(sec_per_km % 60)
    return f"{p_min:02d}:{p_sec:02d} /km"


def _describe_distance_and_time(sport_type: str, dist_km: float, duration_s: float) -> str:
    """Produces heuristic text describing the distance and duration."""
    sport = (sport_type or "").lower()
    dur_str = _format_duration(duration_s)

    if any(k in sport for k in ("hik", "walk", "berg", "climb")):
        if dist_km < 6.0:
            tier = "Eine kürzere, gemütliche Tour zum Durchatmen und Genießen."
        elif dist_km < 13.0:
            tier = "Eine abwechslungsreiche Strecke mit guter Länge im angenehmen Wanderbereich."
        elif dist_km < 22.0:
            tier = "Eine fordernde, ausgedehnte Tagestour mit ordentlicher Kilometerleistung."
        else:
            tier = "Eine echte Langstrecken-Wanderung, die Ausdauer und feste Schritte verlangte."
        return f"Über eine Strecke von **{dist_km:.1f} km** war ich insgesamt **{dur_str}** unterwegs. {tier}"

    if any(k in sport for k in ("run", "lauf", "trail")):
        if dist_km < 6.0:
            tier = "Ein entspannter, kurzer Lauf zum Einrollen und Beine lockern."
        elif dist_km < 12.0:
            tier = "Ein solider Ausdauerlauf mit gutem Trainingsrhythmus."
        elif dist_km < 21.1:
            tier = "Ein langer, anspruchsvoller Dauerlauf über eine beachtliche Distanz."
        else:
            tier = "Ein Lauf im Halbmarathon- bzw. Langstreckenformat mit hohem Energieaufwand."
        return f"Die Laufdistanz betrug **{dist_km:.1f} km** bei einer Zeit von **{dur_str}**. {tier}"

    if any(k in sport for k in ("cycl", "bike", "rad")):
        if dist_km < 25.0:
            tier = "Eine flotte Feierabend- oder Genussrunde auf zwei Rädern."
        elif dist_km < 55.0:
            tier = "Eine ausgedehnte Ausfahrt mit gutem Schnitt und schöner Streckenführung."
        elif dist_km < 90.0:
            tier = "Eine lange, konditionell fordernde Trainingsausfahrt."
        else:
            tier = "Ein echter Gran Fondo / Langstreckenritt mit sattem Kilometerpensum."
        return f"Insgesamt wurden **{dist_km:.1f} km** in **{dur_str}** zurückgelegt. {tier}"

    return f"Die Aktivität umfasste eine Distanz von **{dist_km:.1f} km** bei einer Gesamtdauer von **{dur_str}**."


def _describe_elevation(gain_m: float | None, max_ele: float | None, min_ele: float | None) -> str:
    """Produces heuristic text describing the elevation profile."""
    if gain_m is None or gain_m < 15.0:
        return "Das Höhenprofil verlief weitgehend eben ohne nennenswerte Steigungen."

    peak_clause = f" (höchster Punkt bei **{max_ele:.0f} m**, Tiefstpunkt bei **{min_ele:.0f} m**)" if max_ele else ""

    if gain_m >= 800:
        return (
            f"Mit beachtlichen **+{gain_m:.0f} Höhenmetern** im Anstieg war das Gelände alpin und "
            f"forderte die Waden ordentlich{peak_clause}."
        )
    if gain_m >= 350:
        return (
            f"Auf der Strecke wurden spürbare **+{gain_m:.0f} Höhenmeter** überwunden{peak_clause}, "
            f"was für lohnende Anstiege und schöne Ausblicke sorgte."
        )
    if gain_m >= 100:
        return f"Ein leicht hügeliges Profil mit moderaten **+{gain_m:.0f} Höhenmetern** im Aufstieg{peak_clause}."

    return f"Mit leichten Wellen und insgesamt **+{gain_m:.0f} Höhenmetern** hielt sich die Steigung im Rahmen."


def _describe_intensity(avg_hr: int | float | None, max_hr: int | float | None) -> str:
    """Produces heuristic text evaluating heart rate intensity."""
    if not avg_hr or avg_hr <= 40:
        return ""

    hr_val = int(avg_hr)
    max_clause = f" (Spitzenpuls: **{int(max_hr)} bpm**)" if max_hr and max_hr > hr_val else ""

    if hr_val < 105:
        return f"Die Herzfrequenz lag mit durchschnittlich **{hr_val} bpm**{max_clause} im entspannten, regenerativen Bereich."
    if hr_val < 135:
        return f"Die Belastung bewegte sich mit durchschnittlich **{hr_val} bpm**{max_clause} in einer soliden aeroben Grundlagenausdauer-Zone."
    if hr_val < 160:
        return f"Bei einem Durchschnittspuls von **{hr_val} bpm**{max_clause} war die Einheit sportlich fordernd und intensiv."
    return f"Mit einem hohen Durchschnittspuls von **{hr_val} bpm**{max_clause} wurde an der Leistungsgrenze gearbeitet."


def generate_deterministic_narrative(
    date_str: str,
    daily_dir: Path,
    activity_dirs: list[Path] | None = None,
    user_notes: str | None = None,
) -> str:
    """Creates a structured, deterministic markdown summary based on activity metrics and heuristics."""
    date_de = format_german_date(date_str)
    lines: list[str] = []

    if not activity_dirs:
        # Standalone daily health entry
        lines.append(f"# 📊 Tagesübersicht & Gesundheitsdaten")
        lines.append(f"*{date_de}*\n")
        lines.append(f"Für den heutigen Tag wurden keine aktiven Trainingseinheiten mit GPS-Aufzeichnung erfasst.")
        if user_notes and user_notes.strip():
            lines.append(f"\n> 📝 **Persönliche Notiz:** {user_notes.strip()}\n")
        return "\n".join(lines)

    # Collect activities info
    act_data_list: list[dict[str, Any]] = []
    for act_dir in activity_dirs:
        raw_act_file = act_dir / "raw_activity.json"
        raw_details_file = act_dir / "raw_details.json"
        data: dict[str, Any] = {
            "dir": act_dir,
            "name": act_dir.name.replace("_", " ").title(),
            "sport": "activity",
            "distance_km": None,
            "duration_s": None,
            "elevation_gain": None,
            "elevation_loss": None,
            "avg_hr": None,
            "max_hr": None,
            "calories": None,
            "location": None,
            "description": None,
            "min_elevation": None,
            "max_elevation": None,
        }

        if raw_act_file.exists():
            try:
                ra = json.loads(raw_act_file.read_text(encoding="utf-8"))
                data["name"] = ra.get("activityName") or data["name"]
                type_obj = ra.get("activityType")
                if isinstance(type_obj, dict):
                    data["sport"] = type_obj.get("typeKey", "activity")
                dist = ra.get("distance")
                if dist:
                    data["distance_km"] = dist / 1000.0
                dur = ra.get("duration") or ra.get("elapsedDuration")
                if dur:
                    data["duration_s"] = dur
                data["elevation_gain"] = ra.get("elevationGain") or ra.get("totalElevationGain")
                data["elevation_loss"] = ra.get("elevationLoss") or ra.get("totalElevationLoss")
                data["avg_hr"] = ra.get("averageHR")
                data["max_hr"] = ra.get("maxHR")
                data["calories"] = ra.get("calories")
                data["location"] = ra.get("locationName")
                data["description"] = ra.get("description")
            except (json.JSONDecodeError, OSError):
                pass

        # Extract elevation stats from telemetry / GPX
        try:
            _, ele_stats = extract_elevation_points(act_dir)
            if ele_stats.get("elevation_gain") is not None and data["elevation_gain"] is None:
                data["elevation_gain"] = ele_stats["elevation_gain"]
            data["min_elevation"] = ele_stats.get("min_elevation")
            data["max_elevation"] = ele_stats.get("max_elevation")
            if data["distance_km"] is None and ele_stats.get("total_distance_km"):
                data["distance_km"] = ele_stats["total_distance_km"]
        except Exception:
            pass

        act_data_list.append(data)

    primary = act_data_list[0]
    sport_cfg = SPORT_CONFIG.get(primary["sport"], {"name": "Aktivität", "verb": "trainieren", "emoji": "⚡"})
    emoji = sport_cfg["emoji"]
    sport_label = sport_cfg["name"]
    loc_suffix = f" in {primary['location']}" if primary.get("location") else ""

    # H1 Header & Date
    lines.append(f"# {emoji} {primary['name']}{loc_suffix}")
    lines.append(f"*{date_de}*\n")

    # User note & Garmin notes
    if user_notes and user_notes.strip():
        lines.append(f"> ✍️ **Persönliche Notiz:** {user_notes.strip()}\n")

    for act in act_data_list:
        desc = act.get("description")
        if desc and desc.strip():
            lines.append(f"> 📝 **Garmin-Notiz ({act['name']}):** {desc.strip()}\n")

    # Narrative paragraphs per activity
    for idx, act in enumerate(act_data_list, 1):
        act_sport_cfg = SPORT_CONFIG.get(act["sport"], {"name": "Aktivität", "verb": "trainieren", "emoji": "⚡"})
        act_emoji = act_sport_cfg["emoji"]
        act_label = act_sport_cfg["name"]

        if len(act_data_list) > 1:
            lines.append(f"### {act_emoji} Teil {idx}: {act['name']}\n")

        # Paragraph 1: Distance & Time
        if act["distance_km"] and act["duration_s"]:
            lines.append(_describe_distance_and_time(act["sport"], act["distance_km"], act["duration_s"]))

        # Paragraph 2: Elevation & Terrain
        ele_text = _describe_elevation(act["elevation_gain"], act["max_elevation"], act["min_elevation"])
        if ele_text:
            lines.append(ele_text)

        # Paragraph 3: Heart Rate & Intensity
        hr_text = _describe_intensity(act["avg_hr"], act["max_hr"])
        if hr_text:
            lines.append(hr_text)

        lines.append("")

        # Metrics Table
        pace_speed = _format_pace_or_speed(act["sport"], act["distance_km"], act["duration_s"])
        table_rows = [
            f"| 📍 **Aktivität & Ort** | {act['name']}{(' (' + act['location'] + ')') if act.get('location') else ''} |",
            f"| {act_emoji} **Sportart** | {act_label} |",
        ]
        if act["distance_km"] is not None:
            table_rows.append(f"| 📏 **Distanz** | {act['distance_km']:.2f} km |")
        if act["duration_s"] is not None:
            table_rows.append(f"| ⏱️ **Dauer** | {_format_duration(act['duration_s'])} |")
        if act["elevation_gain"] is not None:
            elev_str = f"+{act['elevation_gain']:.0f} m"
            if act["elevation_loss"] is not None:
                elev_str += f" / -{act['elevation_loss']:.0f} m"
            table_rows.append(f"| ⛰️ **Höhenmeter** | {elev_str} |")
        if act["avg_hr"] is not None:
            hr_str = f"{int(act['avg_hr'])} bpm"
            if act["max_hr"]:
                hr_str += f" (Max: {int(act['max_hr'])} bpm)"
            table_rows.append(f"| 💓 **Herzfrequenz** | {hr_str} |")
        if pace_speed != "-":
            metric_name = "Geschwindigkeit" if "km/h" in pace_speed else "Durchschnittspace"
            table_rows.append(f"| ⚡ **{metric_name}** | {pace_speed} |")
        if act["calories"]:
            table_rows.append(f"| 🔥 **Kalorienverbrauch** | {act['calories']:,} kcal |")

        lines.extend(
            [
                "| Kennzahl | Wert |",
                "| :--- | :--- |",
                *table_rows,
                "",
            ]
        )

    # Daily health summary (sleep, steps, stress) if available
    daily_sum_file = daily_dir / "daily_summary.md"
    if daily_sum_file.exists():
        daily_text = daily_sum_file.read_text(encoding="utf-8")
        lines.append("### 💤 Schlaf & Tagesgesundheit\n")
        bullets = [line.strip() for line in daily_text.splitlines() if line.strip().startswith("- ")]
        if bullets:
            lines.extend(bullets[:8])
            lines.append("")

    return "\n".join(lines)


def generate_deterministic_daily_story(
    date_str: str,
    daily_dir: Path,
    activity_dirs: list[Path] | None = None,
    user_notes: str | None = None,
) -> tuple[Path, str]:
    """Generates the full self-contained report using deterministic heuristics and interactive media blocks (0 API tokens)."""
    narrative_text = generate_deterministic_narrative(
        date_str=date_str,
        daily_dir=daily_dir,
        activity_dirs=activity_dirs,
        user_notes=user_notes,
    )

    full_markdown = assemble_self_contained_diary(
        date_str=date_str,
        narrative_text=narrative_text,
        daily_dir=daily_dir,
        activity_dirs=activity_dirs,
    )

    output_file = daily_dir / "daily_story.md"
    daily_dir.mkdir(parents=True, exist_ok=True)
    output_file.write_text(full_markdown, encoding="utf-8")

    logger.info("Saved deterministic daily story to %s (length: %d chars)", output_file, len(full_markdown))
    return output_file, full_markdown
