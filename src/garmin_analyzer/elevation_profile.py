"""Elevation profile analysis and visualization for activities."""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from garmin_analyzer.gps_map import parse_gpx_points

logger = logging.getLogger(__name__)

# Dark theme palette matching gps_map.py and visualizer.py
COLOR_BG = "#0f141c"
COLOR_CARD = "#171f2c"
COLOR_GRID = "#26354a"
COLOR_TEXT = "#e2e8f0"
COLOR_TEXT_MUTED = "#94a3b8"
COLOR_ACCENT = "#38bdf8"      # Cyan / sky-400
COLOR_ACCENT_FILL = "#0284c7" # Sky-600
COLOR_PEAK = "#f43f5e"        # Rose-500 for maximum elevation


def _haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates great-circle distance between two GPS coordinates in meters."""
    r = 6371000.0  # Earth radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def extract_elevation_points(
    act_dir: Path | str,
) -> tuple[list[tuple[float, float]], dict[str, float | None]]:
    """Extracts elevation profile points (distance_km, elevation_m) and summary stats.

    Tries sensor metrics from raw_details.json first, falls back to track.gpx trackpoints.
    """
    path = Path(act_dir)
    if not path.is_dir():
        path = path.parent

    details_file = path / "raw_details.json"
    gpx_file = path / "track.gpx"

    points: list[tuple[float, float]] = []

    # 1. Try raw_details.json (calibrated Garmin device telemetry)
    if details_file.exists():
        try:
            rd = json.loads(details_file.read_text(encoding="utf-8"))
            descriptors = {
                m.get("key"): m.get("metricsIndex")
                for m in rd.get("metricDescriptors", [])
                if isinstance(m, dict)
            }
            ele_idx = descriptors.get("directElevation")
            dist_idx = descriptors.get("sumDistance")

            if ele_idx is not None and dist_idx is not None:
                for item in rd.get("activityDetailMetrics", []):
                    m = item.get("metrics", [])
                    if len(m) > max(ele_idx, dist_idx):
                        e = m[ele_idx]
                        d = m[dist_idx]
                        if e is not None and d is not None:
                            points.append((round(float(d) / 1000.0, 3), round(float(e), 1)))
        except (OSError, json.JSONDecodeError, KeyError, ValueError) as err:
            logger.debug("Could not parse elevation metrics from %s: %s", details_file, err)

    # 2. Fallback to track.gpx if no points from raw_details
    if len(points) < 2 and gpx_file.exists():
        try:
            raw_pts = parse_gpx_points(gpx_file)
            if len(raw_pts) >= 2:
                cum_dist_m = 0.0
                gpx_pts: list[tuple[float, float]] = [
                    (0.0, round(float(raw_pts[0].get("ele") or 0.0), 1))
                ]
                for i in range(1, len(raw_pts)):
                    d = _haversine_distance_m(
                        raw_pts[i - 1]["lat"],
                        raw_pts[i - 1]["lon"],
                        raw_pts[i]["lat"],
                        raw_pts[i]["lon"],
                    )
                    cum_dist_m += d
                    ele = raw_pts[i].get("ele")
                    if ele is not None:
                        gpx_pts.append((round(cum_dist_m / 1000.0, 3), round(float(ele), 1)))
                if len(gpx_pts) >= 2:
                    points = gpx_pts
        except (OSError, ValueError) as err:
            logger.debug("Could not parse elevation from GPX %s: %s", gpx_file, err)

    if len(points) < 2:
        return [], {
            "min_elevation": None,
            "max_elevation": None,
            "elevation_gain": None,
            "elevation_loss": None,
            "total_distance_km": None,
            "start_elevation": None,
            "end_elevation": None,
        }

    # Ensure strictly sorted by distance
    points.sort(key=lambda p: p[0])

    elevations = [p[1] for p in points]
    min_ele = min(elevations)
    max_ele = max(elevations)
    start_ele = elevations[0]
    end_ele = elevations[-1]
    total_dist = points[-1][0]

    # Calculate gain and loss
    gain = 0.0
    loss = 0.0
    for i in range(1, len(elevations)):
        diff = elevations[i] - elevations[i - 1]
        if diff > 0:
            gain += diff
        else:
            loss += abs(diff)

    stats = {
        "min_elevation": round(min_ele, 1),
        "max_elevation": round(max_ele, 1),
        "elevation_gain": round(gain, 1),
        "elevation_loss": round(loss, 1),
        "total_distance_km": round(total_dist, 2),
        "start_elevation": round(start_ele, 1),
        "end_elevation": round(end_ele, 1),
    }

    return points, stats


def render_elevation_profile(
    act_dir: Path | str,
    output_path: Path | str,
    title: str = "Höhenprofil",
    distance_km: float | None = None,
    elevation_gain_m: float | None = None,
) -> Path | None:
    """Renders a sleek modern dark-mode elevation profile chart as PNG."""
    points, stats = extract_elevation_points(act_dir)
    if len(points) < 2:
        logger.debug("Insufficient elevation points in %s to render profile", act_dir)
        return None

    out_p = Path(output_path)
    distances = np.array([p[0] for p in points])
    elevations = np.array([p[1] for p in points])

    min_val = stats["min_elevation"] or np.min(elevations)
    max_val = stats["max_elevation"] or np.max(elevations)
    gain_val = elevation_gain_m if elevation_gain_m is not None else stats["elevation_gain"]
    dist_val = distance_km if distance_km is not None else stats["total_distance_km"]

    # Baseline for area fill slightly below minimum elevation and generous top headroom
    y_min_margin = max(15.0, (max_val - min_val) * 0.12)
    y_bottom = max(0.0, min_val - y_min_margin)
    y_top = max_val + max(28.0, (max_val - min_val) * 0.22)

    fig, ax = plt.subplots(figsize=(10, 4.5), facecolor=COLOR_BG)
    ax.set_facecolor(COLOR_CARD)

    # Gradient-like filled area under elevation curve
    ax.fill_between(
        distances,
        elevations,
        y_bottom,
        color=COLOR_ACCENT_FILL,
        alpha=0.35,
        zorder=2,
    )
    # Highlight elevation contour line
    ax.plot(distances, elevations, color=COLOR_ACCENT, linewidth=2.4, zorder=3)

    # Highlight peak elevation point
    peak_idx = int(np.argmax(elevations))
    peak_dist = distances[peak_idx]
    peak_ele = elevations[peak_idx]
    ax.scatter(
        [peak_dist],
        [peak_ele],
        color=COLOR_PEAK,
        s=60,
        zorder=5,
        edgecolors=COLOR_BG,
        linewidths=1.5,
    )
    ax.annotate(
        f"Gipfel: {peak_ele:.0f} m",
        (peak_dist, peak_ele),
        textcoords="offset points",
        xytext=(0, 10),
        ha="center",
        color=COLOR_TEXT,
        fontsize=8.5,
        fontweight="bold",
        bbox={
            "facecolor": COLOR_BG,
            "edgecolor": COLOR_PEAK,
            "boxstyle": "round,pad=0.3",
            "alpha": 0.85,
        },
        zorder=6,
    )

    # Grid & styling
    ax.set_ylim(y_bottom, y_top)
    ax.set_xlim(distances[0], distances[-1])
    ax.grid(True, linestyle="--", color=COLOR_GRID, alpha=0.5, zorder=1)

    for spine in ax.spines.values():
        spine.set_color(COLOR_GRID)

    ax.tick_params(colors=COLOR_TEXT_MUTED, labelsize=9)
    ax.set_xlabel("Distanz (km)", color=COLOR_TEXT_MUTED, fontsize=10, labelpad=8)
    ax.set_ylabel("Höhe über NN (m)", color=COLOR_TEXT_MUTED, fontsize=10, labelpad=8)

    # Title and stats subtitle
    ax.set_title(title, fontsize=13, fontweight="bold", color=COLOR_TEXT, pad=20)

    badge_items: list[str] = []
    if dist_val is not None:
        badge_items.append(f"Distanz: {dist_val:.1f} km")
    if gain_val is not None:
        badge_items.append(f"Anstieg: +{gain_val:.0f} m")
    badge_items.append(f"Min: {min_val:.0f} m")
    badge_items.append(f"Max: {max_val:.0f} m")

    if badge_items:
        badge_text = " • ".join(badge_items)
        ax.text(
            0.5,
            1.02,
            badge_text,
            transform=ax.transAxes,
            color=COLOR_TEXT_MUTED,
            fontsize=8.5,
            fontweight="500",
            ha="center",
            va="bottom",
            zorder=6,
        )

    plt.tight_layout()
    out_p.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_p, dpi=180, facecolor=COLOR_BG)
    plt.close(fig)

    logger.info("Saved elevation profile to %s", out_p)
    return out_p


def generate_elevation_plotly_spec(
    act_dir: Path | str,
    title: str = "Höhenprofil",
    max_points: int = 1200,
) -> dict[str, Any] | None:
    """Generates an interactive Plotly specification for the elevation profile."""
    points, stats = extract_elevation_points(act_dir)
    if len(points) < 2:
        return None

    # Downsample if track has thousands of points to keep markdown lightweight
    if len(points) > max_points:
        step = len(points) / max_points
        sampled = [points[int(i * step)] for i in range(max_points - 1)]
        sampled.append(points[-1])
        points = sampled

    x_vals = [p[0] for p in points]
    y_vals = [p[1] for p in points]

    min_val = stats["min_elevation"] or min(y_vals)
    max_val = stats["max_elevation"] or max(y_vals)
    gain_val = stats["elevation_gain"]

    sub_title = f"Min: {min_val:.0f} m • Max: {max_val:.0f} m"
    if gain_val is not None:
        sub_title = f"Anstieg: +{gain_val:.0f} m • {sub_title}"

    spec = {
        "data": [
            {
                "type": "scatter",
                "mode": "lines",
                "name": "Höhe (m)",
                "x": x_vals,
                "y": y_vals,
                "fill": "tozeroy",
                "fillcolor": "rgba(56, 189, 248, 0.22)",
                "line": {"color": "#38bdf8", "width": 2.5, "shape": "linear"},
                "hovertemplate": "<b>Distanz:</b> %{x:.2f} km<br><b>Höhe:</b> %{y:.0f} m<extra></extra>",
            }
        ],
        "layout": {
            "title": {
                "text": f"<b>{title}</b><br><span style='font-size: 11px; color: #94a3b8;'>{sub_title}</span>",
                "font": {"color": "#f8fafc", "size": 15},
            },
            "paper_bgcolor": "#171f2c",
            "plot_bgcolor": "#171f2c",
            "font": {"color": "#e2e8f0", "family": "Inter, system-ui, sans-serif"},
            "xaxis": {
                "title": "Distanz (km)",
                "gridcolor": "#26354a",
                "zeroline": False,
                "color": "#94a3b8",
            },
            "yaxis": {
                "title": "Höhe über NN (m)",
                "gridcolor": "#26354a",
                "zeroline": False,
                "color": "#94a3b8",
            },
            "margin": {"l": 55, "r": 25, "t": 60, "b": 45},
            "hovermode": "x unified",
        },
    }
    return spec


def generate_elevation_markdown_block(
    act_dir: Path | str,
    title: str = "Höhenprofil",
) -> str:
    """Generates a ```plotly code block for the interactive elevation profile."""
    spec = generate_elevation_plotly_spec(act_dir, title=title)
    if not spec:
        return ""
    json_str = json.dumps(spec, indent=2)
    return f"```plotly\n{json_str}\n```\n"
