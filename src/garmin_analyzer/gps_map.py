"""GPS route map visualization using Matplotlib."""

from __future__ import annotations

import json
import logging
import math
import xml.etree.ElementTree as ET
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np

matplotlib.use("Agg")

logger = logging.getLogger(__name__)

# Dark theme palette matching visualizer.py
COLOR_BG = "#0f141c"
COLOR_CARD = "#171f2c"
COLOR_GRID = "#26354a"
COLOR_TEXT = "#e2e8f0"
COLOR_TEXT_MUTED = "#94a3b8"
COLOR_ROUTE = "#00e5ff"
COLOR_START = "#00e676"
COLOR_FINISH = "#ff3d71"


def parse_gpx_points(gpx_path: Path | str) -> list[dict[str, float]]:
    """Parses trackpoints from a GPX file into a list of dicts with lat, lon, ele."""
    path = Path(gpx_path)
    if not path.exists():
        return []

    try:
        tree = ET.parse(path)
        root = tree.getroot()

        # Handle GPX namespaces dynamically
        points: list[dict[str, float]] = []
        for elem in root.iter():
            if elem.tag.endswith("trkpt"):
                lat_str = elem.attrib.get("lat")
                lon_str = elem.attrib.get("lon")
                if lat_str is None or lon_str is None:
                    continue
                try:
                    lat = float(lat_str)
                    lon = float(lon_str)
                except ValueError:
                    continue

                ele = None
                for child in elem:
                    if child.tag.endswith("ele") and child.text:
                        try:
                            ele = float(child.text)
                        except ValueError:
                            pass

                points.append({"lat": lat, "lon": lon, "ele": ele or 0.0})

        return points
    except (ET.ParseError, OSError) as e:
        logger.warning("Failed parsing GPX file %s: %s", path, e)
        return []


def render_gps_map(
    gpx_path: Path | str,
    output_path: Path | str,
    title: str = "Activity Route",
    distance_km: float | None = None,
    elevation_gain_m: float | None = None,
) -> Path | None:
    """Renders a sleek dark-mode GPS route map from a GPX file."""
    gpx_p = Path(gpx_path)
    out_p = Path(output_path)
    points = parse_gpx_points(gpx_p)

    if len(points) < 2:
        logger.debug("Not enough trackpoints to render map in %s", gpx_p)
        return None

    lats = [p["lat"] for p in points]
    lons = [p["lon"] for p in points]
    eles = [p["ele"] for p in points]

    fig, ax = plt.subplots(figsize=(9, 6), facecolor=COLOR_BG)
    ax.set_facecolor(COLOR_CARD)

    # Correct for aspect ratio based on latitude
    mean_lat = np.mean(lats)
    aspect_correction = 1.0 / math.cos(math.radians(mean_lat))
    ax.set_aspect(aspect_correction)

    # Route line: subtle shadow line underneath, vibrant line on top
    ax.plot(lons, lats, color="#000000", linewidth=5.5, alpha=0.5, zorder=3)
    ax.plot(
        lons,
        lats,
        color=COLOR_ROUTE,
        linewidth=3.0,
        alpha=0.95,
        solid_capstyle="round",
        zorder=4,
        label="Route",
    )

    # Start and Finish markers
    ax.scatter(
        [lons[0]],
        [lats[0]],
        color=COLOR_START,
        s=120,
        edgecolors="#ffffff",
        linewidth=1.8,
        zorder=5,
        label="Start",
    )
    ax.scatter(
        [lons[-1]],
        [lats[-1]],
        color=COLOR_FINISH,
        s=120,
        edgecolors="#ffffff",
        linewidth=1.8,
        zorder=5,
        label="Finish",
    )

    # Styling grid & spines
    ax.grid(True, color=COLOR_GRID, linestyle="--", linewidth=0.6, alpha=0.6)
    for spine in ax.spines.values():
        spine.set_color(COLOR_GRID)
        spine.set_linewidth(1.0)

    ax.tick_params(colors=COLOR_TEXT_MUTED, labelsize=9)
    ax.set_xlabel("Longitude", color=COLOR_TEXT_MUTED, fontsize=9.5, labelpad=6)
    ax.set_ylabel("Latitude", color=COLOR_TEXT_MUTED, fontsize=9.5, labelpad=6)

    # Title
    ax.set_title(
        f"Route: {title}",
        color=COLOR_TEXT,
        fontsize=13,
        fontweight="bold",
        pad=14,
        loc="left",
    )

    # Legend
    legend = ax.legend(
        loc="upper right",
        facecolor=COLOR_CARD,
        edgecolor=COLOR_GRID,
        labelcolor=COLOR_TEXT,
        fontsize=9,
        framealpha=0.85,
    )
    legend.get_frame().set_linewidth(0.8)

    # Metrics Badge Box in lower left
    badge_items = []
    if distance_km is not None:
        badge_items.append(f"Dist: {distance_km:.2f} km")
    if elevation_gain_m is not None:
        badge_items.append(f"Gain: +{elevation_gain_m:.0f} m")
    elif max(eles) > 0 and min(eles) > 0:
        badge_items.append(f"Ele: {min(eles):.0f}m - {max(eles):.0f}m")

    if badge_items:
        badge_text = " • ".join(badge_items)
        ax.text(
            0.025,
            0.04,
            badge_text,
            transform=ax.transAxes,
            color=COLOR_TEXT,
            fontsize=9.5,
            fontweight="bold",
            bbox={
                "facecolor": COLOR_CARD,
                "edgecolor": COLOR_ROUTE,
                "boxstyle": "round,pad=0.5",
                "alpha": 0.9,
                "linewidth": 1.2,
            },
            zorder=6,
        )

    plt.tight_layout()
    out_p.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_p, dpi=180, facecolor=COLOR_BG)
    plt.close(fig)

    logger.info("Saved GPS route map to %s", out_p)
    return out_p


def gpx_to_leaflet_spec(
    gpx_path: Path | str,
    title: str = "Route",
    distance_km: float | None = None,
    elevation_gain_m: float | None = None,
    max_points: int = 1500,
) -> dict | None:
    """Extracts trackpoints from GPX and builds an interactive Leaflet route specification."""
    points = parse_gpx_points(gpx_path)
    if len(points) < 2:
        return None

    # Downsample evenly if too many points to avoid massive markdown sizes
    if len(points) > max_points:
        step = len(points) / max_points
        sampled = [points[int(i * step)] for i in range(max_points - 1)]
        sampled.append(points[-1])
        points = sampled

    lats = [p["lat"] for p in points]
    lons = [p["lon"] for p in points]
    center_lat = round(float(np.mean(lats)), 6)
    center_lon = round(float(np.mean(lons)), 6)

    coords = [[round(p["lat"], 6), round(p["lon"], 6)] for p in points]

    spec = {
        "title": title,
        "distance_km": round(distance_km, 2) if distance_km is not None else None,
        "elevation_gain_m": round(elevation_gain_m, 1) if elevation_gain_m is not None else None,
        "center": [center_lat, center_lon],
        "coordinates": coords,
    }
    return spec


def generate_leaflet_markdown_block(
    gpx_path: Path | str,
    title: str = "Route",
    distance_km: float | None = None,
    elevation_gain_m: float | None = None,
) -> str:
    """Generates a ```leaflet code block containing the interactive route specification."""
    spec = gpx_to_leaflet_spec(
        gpx_path=gpx_path,
        title=title,
        distance_km=distance_km,
        elevation_gain_m=elevation_gain_m,
    )
    if not spec:
        return ""

    json_str = json.dumps(spec, indent=2)
    return f"```leaflet\n{json_str}\n```\n"

