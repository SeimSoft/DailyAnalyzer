"""Visualizations for daily health metrics (Heart Rate, Stress, Body Battery, HRV)."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import matplotlib

# Set non-interactive backend for headless execution
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

logger = logging.getLogger(__name__)

# Modern Dark Theme Palette
BG_COLOR = "#0f172a"  # Slate 900
PANEL_COLOR = "#1e293b"  # Slate 800
TEXT_COLOR = "#f8fafc"  # Slate 50
SUBTEXT_COLOR = "#94a3b8"  # Slate 400
GRID_COLOR = "#334155"  # Slate 700


def _setup_figure(
    title: str, xlabel: str = "Time", ylabel: str = ""
) -> tuple[plt.Figure, plt.Axes]:
    """Creates a styled matplotlib figure with dark modern aesthetics."""
    fig, ax = plt.subplots(figsize=(10, 4.5), dpi=150)
    fig.patch.set_facecolor(BG_COLOR)
    ax.set_facecolor(PANEL_COLOR)

    ax.set_title(title, fontsize=13, fontweight="bold", color=TEXT_COLOR, pad=12)
    ax.set_xlabel(xlabel, fontsize=10, color=SUBTEXT_COLOR, labelpad=8)
    ax.set_ylabel(ylabel, fontsize=10, color=SUBTEXT_COLOR, labelpad=8)

    ax.tick_params(colors=SUBTEXT_COLOR, labelsize=9)
    ax.grid(True, linestyle="--", alpha=0.3, color=GRID_COLOR)

    for spine in ax.spines.values():
        spine.set_color(GRID_COLOR)

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    return fig, ax


def plot_heart_rate_vs_time(raw_data: dict[str, Any], output_dir: Path) -> Path | None:
    """Plots heart rate readings throughout the day."""
    hr_data = raw_data.get("heart_rates") or {}
    hr_values = hr_data.get("heartRateValues") or []
    date_str = raw_data.get("date", "")

    times = []
    values = []
    for item in hr_values:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            ts, val = item[0], item[1]
            if val is not None and val > 30:
                times.append(datetime.fromtimestamp(ts / 1000.0, tz=UTC))
                values.append(val)

    if not times:
        logger.debug("No valid heart rate timeseries points found for %s", date_str)
        return None

    fig, ax = _setup_figure(f"Heart Rate vs Time ({date_str})", ylabel="Heart Rate (bpm)")
    line_color = "#ef4444"  # Red

    ax.plot(times, values, color=line_color, linewidth=1.5, label="Heart Rate")
    ax.fill_between(times, values, min(values) - 5, color=line_color, alpha=0.15)

    rhr = hr_data.get("restingHeartRate")
    if rhr:
        ax.axhline(
            rhr, color="#10b981", linestyle="--", linewidth=1.2, label=f"Resting HR ({rhr} bpm)"
        )

    max_hr = hr_data.get("maxHeartRate")
    if max_hr:
        ax.axhline(
            max_hr, color="#f59e0b", linestyle=":", linewidth=1.0, label=f"Max HR ({max_hr} bpm)"
        )

    ax.legend(facecolor=PANEL_COLOR, edgecolor=GRID_COLOR, labelcolor=TEXT_COLOR, fontsize=9)
    fig.tight_layout()

    out_file = output_dir / "heart_rate_vs_time.png"
    fig.savefig(out_file, facecolor=BG_COLOR)
    fig.savefig(output_dir / "heart_rate_vs_time.svg", facecolor=BG_COLOR)
    plt.close(fig)
    return out_file


def plot_stress_vs_time(raw_data: dict[str, Any], output_dir: Path) -> Path | None:
    """Plots stress level throughout the day with color zones."""
    stress_data = raw_data.get("stress") or {}
    stress_values = stress_data.get("stressValuesArray") or []
    date_str = raw_data.get("date", "")

    times = []
    values = []
    for item in stress_values:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            ts, val = item[0], item[1]
            if val is not None and val >= 0:
                times.append(datetime.fromtimestamp(ts / 1000.0, tz=UTC))
                values.append(val)

    if not times:
        logger.debug("No valid stress timeseries points found for %s", date_str)
        return None

    fig, ax = _setup_figure(f"Stress vs Time ({date_str})", ylabel="Stress Level (0-100)")
    ax.set_ylim(-2, 102)

    # Shaded stress zones
    ax.axhspan(0, 25, color="#3b82f6", alpha=0.12, label="Rest (0-25)")
    ax.axhspan(25, 50, color="#f59e0b", alpha=0.12, label="Low (25-50)")
    ax.axhspan(50, 75, color="#f97316", alpha=0.12, label="Medium (50-75)")
    ax.axhspan(75, 100, color="#ef4444", alpha=0.12, label="High (75-100)")

    ax.plot(times, values, color="#fbbf24", linewidth=1.5, label="Stress Level")

    avg_stress = stress_data.get("avgStressLevel")
    if avg_stress:
        ax.axhline(
            avg_stress,
            color="#ec4899",
            linestyle="--",
            linewidth=1.2,
            label=f"Avg Stress ({avg_stress})",
        )

    ax.legend(
        facecolor=PANEL_COLOR,
        edgecolor=GRID_COLOR,
        labelcolor=TEXT_COLOR,
        fontsize=8,
        loc="upper right",
    )
    fig.tight_layout()

    out_file = output_dir / "stress_vs_time.png"
    fig.savefig(out_file, facecolor=BG_COLOR)
    fig.savefig(output_dir / "stress_vs_time.svg", facecolor=BG_COLOR)
    plt.close(fig)
    return out_file


def plot_body_battery_vs_time(raw_data: dict[str, Any], output_dir: Path) -> Path | None:
    """Plots body battery energy level curve throughout the day."""
    bb_list = raw_data.get("body_battery") or []
    if not isinstance(bb_list, list) or not bb_list:
        return None

    first_entry = bb_list[0]
    bb_values = first_entry.get("bodyBatteryValuesArray") or []
    date_str = raw_data.get("date", "")

    times = []
    values = []
    for item in bb_values:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            ts, val = item[0], item[1]
            if val is not None and val >= 0:
                times.append(datetime.fromtimestamp(ts / 1000.0, tz=UTC))
                values.append(val)

    if not times:
        logger.debug("No valid body battery timeseries points found for %s", date_str)
        return None

    fig, ax = _setup_figure(f"Body Battery vs Time ({date_str})", ylabel="Body Battery (%)")
    ax.set_ylim(-2, 102)
    line_color = "#06b6d4"  # Cyan

    ax.plot(times, values, color=line_color, linewidth=2.0, label="Body Battery")
    ax.fill_between(times, values, 0, color=line_color, alpha=0.15)

    charged = first_entry.get("charged")
    drained = first_entry.get("drained")
    label_suffix = []
    if charged is not None:
        label_suffix.append(f"+{charged} chg")
    if drained is not None:
        label_suffix.append(f"-{drained} drn")

    title_label = f"Energy Curve ({', '.join(label_suffix)})" if label_suffix else "Energy Curve"
    ax.plot([], [], " ", label=title_label)

    ax.legend(facecolor=PANEL_COLOR, edgecolor=GRID_COLOR, labelcolor=TEXT_COLOR, fontsize=9)
    fig.tight_layout()

    out_file = output_dir / "body_battery_vs_time.png"
    fig.savefig(out_file, facecolor=BG_COLOR)
    fig.savefig(output_dir / "body_battery_vs_time.svg", facecolor=BG_COLOR)
    plt.close(fig)
    return out_file


def plot_hrv_vs_time(raw_data: dict[str, Any], output_dir: Path) -> Path | None:
    """Plots overnight 5-minute HRV readings and baseline range."""
    hrv_data = raw_data.get("hrv") or {}
    readings = hrv_data.get("hrvReadings") or []
    date_str = raw_data.get("date", "")

    times = []
    values = []
    for r in readings:
        if isinstance(r, dict):
            val = r.get("hrvValue")
            time_str = r.get("readingTimeLocal") or r.get("readingTimeGMT")
            if val is not None and time_str:
                try:
                    dt = datetime.fromisoformat(time_str.split(".")[0])
                    times.append(dt)
                    values.append(val)
                except (ValueError, TypeError, IndexError) as err:
                    logger.debug("Failed parsing HRV timestamp '%s': %s", time_str, err)

    if not times:
        logger.debug("No valid HRV readings found for %s", date_str)
        return None

    fig, ax = _setup_figure(f"HRV vs Time ({date_str})", xlabel="Overnight Time", ylabel="HRV (ms)")
    line_color = "#10b981"  # Emerald

    hrv_summary = hrv_data.get("hrvSummary") or {}
    baseline = hrv_summary.get("baseline") or {}
    low = baseline.get("balancedLow") or baseline.get("lowUpper")
    high = baseline.get("balancedUpper")

    if low and high:
        ax.axhspan(
            low, high, color="#10b981", alpha=0.15, label=f"Baseline ({low:.0f}-{high:.0f} ms)"
        )

    weekly_avg = hrv_summary.get("weeklyAvg")
    if weekly_avg:
        ax.axhline(
            weekly_avg,
            color="#38bdf8",
            linestyle="--",
            linewidth=1.2,
            label=f"7d Avg ({weekly_avg:.0f} ms)",
        )

    ax.plot(
        times, values, color=line_color, marker="o", markersize=3, linewidth=1.5, label="5-min HRV"
    )

    status = hrv_summary.get("status")
    last_night = hrv_summary.get("lastNightAvg")
    info_text = f"Status: {status or 'N/A'}"
    if last_night:
        info_text += f" | Avg: {last_night:.0f} ms"
    ax.set_title(f"HRV vs Time ({date_str}) • {info_text}", fontsize=12, color=TEXT_COLOR)

    ax.legend(facecolor=PANEL_COLOR, edgecolor=GRID_COLOR, labelcolor=TEXT_COLOR, fontsize=8)
    fig.tight_layout()

    out_file = output_dir / "hrv_vs_time.png"
    fig.savefig(out_file, facecolor=BG_COLOR)
    fig.savefig(output_dir / "hrv_vs_time.svg", facecolor=BG_COLOR)
    plt.close(fig)
    return out_file


def generate_all_daily_visualizations(raw_data: dict[str, Any], output_dir: Path) -> list[Path]:
    """Generates all daily health charts and returns list of created image file paths."""
    charts_dir = output_dir / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    created_files: list[Path] = []

    f_hr = plot_heart_rate_vs_time(raw_data, charts_dir)
    if f_hr:
        created_files.append(f_hr)

    f_stress = plot_stress_vs_time(raw_data, charts_dir)
    if f_stress:
        created_files.append(f_stress)

    f_bb = plot_body_battery_vs_time(raw_data, charts_dir)
    if f_bb:
        created_files.append(f_bb)

    f_hrv = plot_hrv_vs_time(raw_data, charts_dir)
    if f_hrv:
        created_files.append(f_hrv)

    return created_files


# -----------------------------------------------------------------------------
# Interactive Plotly Specifications
# -----------------------------------------------------------------------------

def generate_heart_rate_plotly_spec(raw_data: dict[str, Any]) -> dict[str, Any] | None:
    """Generates an interactive Plotly specification for 24h Heart Rate."""
    hr_data = raw_data.get("heart_rates") or {}
    hr_values = hr_data.get("heartRateValues") or []
    date_str = raw_data.get("date", "")

    times = []
    values = []
    for item in hr_values:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            ts, val = item[0], item[1]
            if val is not None and val > 30:
                dt = datetime.fromtimestamp(ts / 1000.0, tz=UTC)
                times.append(dt.strftime("%Y-%m-%d %H:%M:%S"))
                values.append(val)

    if not times:
        return None

    rhr = hr_data.get("restingHeartRate")
    max_hr = hr_data.get("maxHeartRate")

    traces = [
        {
            "x": times,
            "y": values,
            "type": "scatter",
            "mode": "lines",
            "name": "Herzfrequenz",
            "line": {"color": "#ef4444", "width": 2},
            "fill": "tozeroy",
            "fillcolor": "rgba(239, 68, 68, 0.12)",
            "hovertemplate": "%{x|%H:%M}: <b>%{y} bpm</b><extra></extra>",
        }
    ]

    shapes = []
    if rhr:
        shapes.append({
            "type": "line",
            "xref": "paper",
            "x0": 0,
            "x1": 1,
            "yref": "y",
            "y0": rhr,
            "y1": rhr,
            "line": {"color": "#10b981", "width": 1.5, "dash": "dash"},
        })
    if max_hr:
        shapes.append({
            "type": "line",
            "xref": "paper",
            "x0": 0,
            "x1": 1,
            "yref": "y",
            "y0": max_hr,
            "y1": max_hr,
            "line": {"color": "#f59e0b", "width": 1.5, "dash": "dot"},
        })

    title_text = f"Herzfrequenz ({date_str})"
    if rhr:
        title_text += f" • Ruhe-HF: {rhr} bpm"
    if max_hr:
        title_text += f" • Max-HF: {max_hr} bpm"

    layout = {
        "title": {"text": title_text, "font": {"color": "#f8fafc", "size": 15}},
        "xaxis": {
            "title": "Uhrzeit",
            "color": "#94a3b8",
            "gridcolor": "#334155",
            "zeroline": False,
        },
        "yaxis": {
            "title": "Herzfrequenz (bpm)",
            "color": "#94a3b8",
            "gridcolor": "#334155",
            "zeroline": False,
        },
        "shapes": shapes,
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "legend": {"font": {"color": "#f8fafc"}, "orientation": "h", "y": -0.2},
        "margin": {"l": 50, "r": 30, "t": 50, "b": 50},
        "hovermode": "x unified",
    }
    return {"data": traces, "layout": layout}


def generate_stress_plotly_spec(raw_data: dict[str, Any]) -> dict[str, Any] | None:
    """Generates an interactive Plotly specification for daily Stress levels."""
    stress_data = raw_data.get("stress") or {}
    stress_values = stress_data.get("stressValuesArray") or []
    date_str = raw_data.get("date", "")

    times = []
    values = []
    for item in stress_values:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            ts, val = item[0], item[1]
            if val is not None and val >= 0:
                dt = datetime.fromtimestamp(ts / 1000.0, tz=UTC)
                times.append(dt.strftime("%Y-%m-%d %H:%M:%S"))
                values.append(val)

    if not times:
        return None

    avg_stress = stress_data.get("avgStressLevel")

    traces = [
        {
            "x": times,
            "y": values,
            "type": "scatter",
            "mode": "lines",
            "name": "Stresslevel",
            "line": {"color": "#f59e0b", "width": 1.8},
            "fill": "tozeroy",
            "fillcolor": "rgba(245, 158, 11, 0.15)",
            "hovertemplate": "%{x|%H:%M}: <b>%{y} / 100</b><extra></extra>",
        }
    ]

    # Shaded stress bands (Rest: 0-25, Low: 25-50, Med: 50-75, High: 75-100)
    shapes = [
        {"type": "rect", "xref": "paper", "x0": 0, "x1": 1, "yref": "y", "y0": 0, "y1": 25, "fillcolor": "rgba(59, 130, 246, 0.08)", "line": {"width": 0}, "layer": "below"},
        {"type": "rect", "xref": "paper", "x0": 0, "x1": 1, "yref": "y", "y0": 25, "y1": 50, "fillcolor": "rgba(245, 158, 11, 0.08)", "line": {"width": 0}, "layer": "below"},
        {"type": "rect", "xref": "paper", "x0": 0, "x1": 1, "yref": "y", "y0": 50, "y1": 75, "fillcolor": "rgba(249, 115, 22, 0.08)", "line": {"width": 0}, "layer": "below"},
        {"type": "rect", "xref": "paper", "x0": 0, "x1": 1, "yref": "y", "y0": 75, "y1": 100, "fillcolor": "rgba(239, 68, 68, 0.08)", "line": {"width": 0}, "layer": "below"},
    ]

    title_text = f"Stresslevel ({date_str})"
    if avg_stress is not None:
        title_text += f" • Ø Stress: {avg_stress}"

    layout = {
        "title": {"text": title_text, "font": {"color": "#f8fafc", "size": 15}},
        "xaxis": {"title": "Uhrzeit", "color": "#94a3b8", "gridcolor": "#334155", "zeroline": False},
        "yaxis": {"title": "Stress (0-100)", "range": [0, 100], "color": "#94a3b8", "gridcolor": "#334155", "zeroline": False},
        "shapes": shapes,
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "legend": {"font": {"color": "#f8fafc"}, "orientation": "h", "y": -0.2},
        "margin": {"l": 50, "r": 30, "t": 50, "b": 50},
        "hovermode": "x unified",
    }
    return {"data": traces, "layout": layout}


def generate_body_battery_plotly_spec(raw_data: dict[str, Any]) -> dict[str, Any] | None:
    """Generates an interactive Plotly specification for Body Battery."""
    bb_list = raw_data.get("body_battery") or []
    if not isinstance(bb_list, list) or not bb_list:
        return None

    first_entry = bb_list[0]
    bb_values = first_entry.get("bodyBatteryValuesArray") or []
    date_str = raw_data.get("date", "")

    times = []
    values = []
    for item in bb_values:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            ts, val = item[0], item[1]
            if val is not None and val >= 0:
                dt = datetime.fromtimestamp(ts / 1000.0, tz=UTC)
                times.append(dt.strftime("%Y-%m-%d %H:%M:%S"))
                values.append(val)

    if not times:
        return None

    charged = first_entry.get("charged")
    drained = first_entry.get("drained")

    traces = [
        {
            "x": times,
            "y": values,
            "type": "scatter",
            "mode": "lines",
            "name": "Body Battery",
            "line": {"color": "#06b6d4", "width": 2.5},
            "fill": "tozeroy",
            "fillcolor": "rgba(6, 182, 212, 0.15)",
            "hovertemplate": "%{x|%H:%M}: <b>%{y}%</b><extra></extra>",
        }
    ]

    title_text = f"Body Battery ({date_str})"
    suffix = []
    if charged is not None:
        suffix.append(f"+{charged} geladen")
    if drained is not None:
        suffix.append(f"-{drained} verbraucht")
    if suffix:
        title_text += f" • {', '.join(suffix)}"

    layout = {
        "title": {"text": title_text, "font": {"color": "#f8fafc", "size": 15}},
        "xaxis": {"title": "Uhrzeit", "color": "#94a3b8", "gridcolor": "#334155", "zeroline": False},
        "yaxis": {"title": "Energielevel (%)", "range": [0, 100], "color": "#94a3b8", "gridcolor": "#334155", "zeroline": False},
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "legend": {"font": {"color": "#f8fafc"}, "orientation": "h", "y": -0.2},
        "margin": {"l": 50, "r": 30, "t": 50, "b": 50},
        "hovermode": "x unified",
    }
    return {"data": traces, "layout": layout}


def generate_hrv_plotly_spec(raw_data: dict[str, Any]) -> dict[str, Any] | None:
    """Generates an interactive Plotly specification for overnight HRV readings."""
    hrv_data = raw_data.get("hrv") or {}
    readings = hrv_data.get("hrvReadings") or []
    date_str = raw_data.get("date", "")

    times = []
    values = []
    for r in readings:
        if isinstance(r, dict):
            val = r.get("hrvValue")
            time_str = r.get("readingTimeLocal") or r.get("readingTimeGMT")
            if val is not None and time_str:
                try:
                    dt = datetime.fromisoformat(time_str.split(".")[0])
                    times.append(dt.strftime("%Y-%m-%d %H:%M:%S"))
                    values.append(val)
                except (ValueError, TypeError, IndexError):
                    pass

    if not times:
        return None

    hrv_summary = hrv_data.get("hrvSummary") or {}
    baseline = hrv_summary.get("baseline") or {}
    low = baseline.get("balancedLow") or baseline.get("lowUpper")
    high = baseline.get("balancedUpper")
    weekly_avg = hrv_summary.get("weeklyAvg")
    last_night = hrv_summary.get("lastNightAvg")

    traces = [
        {
            "x": times,
            "y": values,
            "type": "scatter",
            "mode": "lines+markers",
            "name": "5-min HRV",
            "line": {"color": "#10b981", "width": 2},
            "marker": {"size": 5, "color": "#10b981"},
            "hovertemplate": "%{x|%H:%M}: <b>%{y} ms</b><extra></extra>",
        }
    ]

    shapes = []
    if low and high:
        shapes.append({
            "type": "rect",
            "xref": "paper",
            "x0": 0,
            "x1": 1,
            "yref": "y",
            "y0": low,
            "y1": high,
            "fillcolor": "rgba(16, 185, 129, 0.12)",
            "line": {"width": 0},
            "layer": "below",
        })
    if weekly_avg:
        shapes.append({
            "type": "line",
            "xref": "paper",
            "x0": 0,
            "x1": 1,
            "yref": "y",
            "y0": weekly_avg,
            "y1": weekly_avg,
            "line": {"color": "#38bdf8", "width": 1.5, "dash": "dash"},
        })

    title_text = f"Nächtlicher HRV-Index ({date_str})"
    if last_night:
        title_text += f" • Ø Nacht: {round(last_night)} ms"
    if weekly_avg:
        title_text += f" • 7-Tage-Ø: {round(weekly_avg)} ms"

    layout = {
        "title": {"text": title_text, "font": {"color": "#f8fafc", "size": 15}},
        "xaxis": {"title": "Uhrzeit", "color": "#94a3b8", "gridcolor": "#334155", "zeroline": False},
        "yaxis": {"title": "HRV (ms)", "color": "#94a3b8", "gridcolor": "#334155", "zeroline": False},
        "shapes": shapes,
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "legend": {"font": {"color": "#f8fafc"}, "orientation": "h", "y": -0.2},
        "margin": {"l": 50, "r": 30, "t": 50, "b": 50},
        "hovermode": "x unified",
    }
    return {"data": traces, "layout": layout}


def generate_daily_biometrics_summary_plotly_spec(raw_data: dict[str, Any]) -> dict[str, Any] | None:
    """Generates an interactive Plotly summary chart comparing daily biometrics against 7-day averages.

    Used when high-resolution 24h intraday curve arrays were purged/archived by Garmin.
    """
    date_str = raw_data.get("date", "")

    hr = raw_data.get("heart_rates") or {}
    rhr = hr.get("restingHeartRate")
    rhr_7d = hr.get("lastSevenDaysAvgRestingHeartRate")

    hrv = raw_data.get("hrv", {}).get("hrvSummary") or {}
    hrv_night = hrv.get("lastNightAvg")
    hrv_7d = hrv.get("weeklyAvg")

    stress = raw_data.get("stress") or {}
    avg_stress = stress.get("avgStressLevel")

    bb_list = raw_data.get("body_battery") or []
    charged = bb_list[0].get("charged") if bb_list else None
    drained = bb_list[0].get("drained") if bb_list else None

    sleep = raw_data.get("sleep", {}).get("dailySleepDTO") or {}
    sleep_score = sleep.get("sleepScores", {}).get("overall", {}).get("value")

    if all(v is None for v in (rhr, hrv_night, avg_stress, charged, sleep_score)):
        return None

    categories: list[str] = []
    tageswerte: list[float | int | None] = []
    vergleichswerte: list[float | int | None] = []
    text_today: list[str] = []
    text_ref: list[str] = []

    if rhr is not None:
        categories.append("Ruhepuls (bpm)")
        tageswerte.append(rhr)
        vergleichswerte.append(rhr_7d if rhr_7d is not None else None)
        text_today.append(f"{rhr} bpm")
        text_ref.append(f"{rhr_7d:.1f} bpm (7d-Ø)" if rhr_7d is not None else "")

    if hrv_night is not None:
        categories.append("HRV (ms)")
        tageswerte.append(hrv_night)
        vergleichswerte.append(hrv_7d if hrv_7d is not None else None)
        text_today.append(f"{hrv_night} ms")
        text_ref.append(f"{hrv_7d:.0f} ms (7d-Ø)" if hrv_7d is not None else "")

    if sleep_score is not None:
        categories.append("Schlaf-Score (/100)")
        tageswerte.append(sleep_score)
        vergleichswerte.append(None)
        text_today.append(f"Score {sleep_score}")
        text_ref.append("")

    if avg_stress is not None:
        categories.append("Stresslevel (/100)")
        tageswerte.append(avg_stress)
        vergleichswerte.append(None)
        text_today.append(f"{avg_stress}/100")
        text_ref.append("")

    if charged is not None or drained is not None:
        categories.append("Body Battery")
        tageswerte.append(charged if charged is not None else 0)
        vergleichswerte.append(drained if drained is not None else None)
        text_today.append(f"+{charged} geladen" if charged is not None else "")
        text_ref.append(f"-{drained} entladen" if drained is not None else "")

    traces = [
        {
            "y": categories,
            "x": tageswerte,
            "name": "Tageswert",
            "type": "bar",
            "orientation": "h",
            "marker": {"color": "#38bdf8"},
            "text": text_today,
            "textposition": "auto",
        },
        {
            "y": categories,
            "x": vergleichswerte,
            "name": "7-Tage-Ø / Vergleich",
            "type": "bar",
            "orientation": "h",
            "marker": {"color": "#94a3b8"},
            "text": text_ref,
            "textposition": "auto",
        },
    ]

    layout = {
        "title": {
            "text": f"Biometrische Tageswerte & Erholung ({date_str})",
            "font": {"color": "#f8fafc", "size": 15},
        },
        "barmode": "group",
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "xaxis": {
            "title": "Messwert",
            "color": "#94a3b8",
            "gridcolor": "#334155",
            "zeroline": False,
        },
        "yaxis": {
            "color": "#f8fafc",
            "autorange": "reversed",
        },
        "legend": {
            "font": {"color": "#f8fafc"},
            "orientation": "h",
            "y": -0.2,
        },
        "margin": {"l": 150, "r": 30, "t": 50, "b": 50},
    }

    return {"data": traces, "layout": layout}


def generate_plotly_markdown_block(spec: dict[str, Any]) -> str:
    """Encodes a Plotly specification into a ```plotly markdown code block."""
    json_str = json.dumps(spec, indent=2)
    return f"```plotly\n{json_str}\n```\n"


def generate_all_interactive_plotly_blocks(raw_data: dict[str, Any]) -> dict[str, str]:
    """Generates all interactive Plotly code blocks available for the day."""
    blocks: dict[str, str] = {}

    hr_spec = generate_heart_rate_plotly_spec(raw_data)
    if hr_spec:
        blocks["heart_rate"] = generate_plotly_markdown_block(hr_spec)

    stress_spec = generate_stress_plotly_spec(raw_data)
    if stress_spec:
        blocks["stress"] = generate_plotly_markdown_block(stress_spec)

    bb_spec = generate_body_battery_plotly_spec(raw_data)
    if bb_spec:
        blocks["body_battery"] = generate_plotly_markdown_block(bb_spec)

    hrv_spec = generate_hrv_plotly_spec(raw_data)
    if hrv_spec:
        blocks["hrv"] = generate_plotly_markdown_block(hrv_spec)

    # Fallback: If no high-resolution intraday curves were available, provide summary biometrics comparison
    if not blocks:
        summary_spec = generate_daily_biometrics_summary_plotly_spec(raw_data)
        if summary_spec:
            blocks["summary_biometrics"] = generate_plotly_markdown_block(summary_spec)

    return blocks

