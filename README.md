# GarminAnalyzer 🏃‍♂️📊📸

A modern Python package (managed with `uv`) to download recent Garmin Connect activities, complete performance statistics, GPS tracks, daily health metrics with 7-day trends, and uploaded activity photos.

## ✨ Features

- 🏃 **What have I done**:
  - Detailed activity metadata: Title, sport, sub-sport, description, event type, local/GMT timestamps, duration, moving duration.
- 📍 **Where was I**:
  - Exact start and end coordinates with direct OpenStreetMap links, elevation profile, location name.
  - Multi-format GPS track export: **GPX** (maps), **TCX** (training platforms), and **Original FIT** file (unpacked binary sensor data).
- 📊 **All Performance Stats**:
  - Distance, pace (min/km), speed (km/h), average & maximum heart rate, calories, cadence, power (avg, max, normalized), elevation gain/loss, aerobic & anaerobic training effect, VO2 max estimate.
  - Lap and split times with split paces and heart rates.
  - Weather conditions at activity start time (temperature, humidity, wind speed & direction, condition).
  - Heart rate time in zones.
  - Full raw JSON payloads (`raw_activity.json`, `raw_details.json`, `splits.json`, `weather.json`, `hr_zones.json`) for 100% telemetry preservation.
- 💓 **Daily Health Stats & 7-Day Trends**:
  - Resting Heart Rate for the day + **7-day average resting HR**.
  - **HRV Index (HFV)**: Overnight average, **7-day average**, HRV baseline range, and status (Balanced / Unbalanced / Low).
  - Steps: Total steps, step goal, and **7-day average steps/day**.
  - Sleep: Total duration, sleep score, and sleep stages (Deep, Light, REM, Awake).
  - Stress level and Body Battery charged/drained.
  - Training readiness and training status.
- 📸 **Uploaded Photos & Images**:
  - Automatically inspects activity metadata and Garmin media endpoints to discover and download any attached photos and images in full resolution.
- 🔐 **Smart Session & Token Caching**:
  - Persists OAuth tokens in `~/.garminconnect_tokens` (or custom directory) so login and MFA prompts only occur once, avoiding Garmin's aggressive rate limiting (HTTP 429).
- 📁 **Organized Directory Layout & Indexes**:
  - Human-friendly Markdown summaries (`activity_summary.md`, `daily_summary.md`) alongside clean JSON models.
  - Auto-generated `activities_index.json` and `activities_index.csv` for easy spreadsheet and data analysis import.

---

## 🚀 Quick Start

### 1. Installation & Environment Setup

This project uses [`uv`](https://docs.astral.sh/uv/) for package and virtual environment management:

```bash
cd /Users/rennekef/Documents/AIApps/GarminAnalyzer
uv sync
```

### 2. Authentication

You can authenticate interactively (recommended) or provide environment variables:

```bash
# Optional: Set environment variables or use .env file
export GARMIN_EMAIL="your_email@example.com"
export GARMIN_PASSWORD="your_password"

# Authenticate and cache session tokens (you will be prompted for MFA if enabled)
uv run garmin-analyzer login
```

Once logged in, tokens are stored in `~/.garminconnect_tokens/`. All future commands use the cached tokens without asking for credentials again.

Check authentication status at any time:
```bash
uv run garmin-analyzer status
```

---

## 💻 CLI Commands

### 1. Download Recent Activities
Downloads your recent activities including all stats, GPS tracks (GPX, TCX, FIT), uploaded photos, and daily health metrics for those days:

```bash
# Download the 10 most recent activities
uv run garmin-analyzer download

# Download 25 recent running activities to a custom directory
uv run garmin-analyzer download --limit 25 --type running --output-dir ./my_garmin_data

# Fast download without tracks or photos
uv run garmin-analyzer download --limit 5 --no-tracks --no-photos
```

### 2. Download All Information for a Specific Day
Downloads complete health metrics and 7-day averages for a particular date:

```bash
# Today's health metrics and 7-day trends
uv run garmin-analyzer daily

# Specific date (supports European format DD.MM.YYYY, ISO YYYY-MM-DD, yesterday, today)
uv run garmin-analyzer daily --date 16.09.2026
uv run garmin-analyzer daily --date 2026-05-15
uv run garmin-analyzer daily --date yesterday
```

This downloads:
- Resting Heart Rate & 7-day average resting HR
- HRV overnight average, 7-day average, baseline, and status
- Steps & 7-day average steps
- Sleep duration, sleep score, and sleep stages
- Stress level & Body Battery
- Training readiness & training status

### 3. Download a Specific Activity by ID
```bash
uv run garmin-analyzer activity 1234567890
```

### 4. Quick List of Activities
Lists recent activities in a clean terminal table without downloading binary files:
```bash
uv run garmin-analyzer list --limit 15
```

---

## 📂 Output Directory Structure

Each downloaded activity is neatly organized in its own directory:

```
garmin_data/
├── activities_index.json                # Master index of all downloaded activities
├── activities_index.csv                 # CSV format ready for Excel/Pandas
├── activities/
│   └── 2026-06-15_11223344_forest_trail_run/
│       ├── activity_summary.md          # Beautiful human-readable markdown report
│       ├── activity_summary.json        # Curated structured metrics
│       ├── raw_activity.json            # Original Garmin activity JSON
│       ├── raw_details.json             # Millisecond-level sensor telemetry
│       ├── splits.json                  # Lap & split metrics
│       ├── weather.json                 # Weather conditions during activity
│       ├── hr_zones.json                # Time in HR zones
│       ├── track.gpx                    # GPS track for Strava / Google Earth / Komoot
│       ├── track.tcx                    # Training Center XML
│       ├── track.fit                    # Raw FIT binary sensor data
│       └── photos/                      # Uploaded photos
│           ├── photo_01_summit.jpg
│           └── photo_02_trail.jpg
└── daily_health/
    └── 2026-06-15/
        ├── daily_summary.md             # Markdown daily health & 7-day trends
        ├── daily_summary.json           # Structured health metrics
        └── raw_daily.json               # Full raw health API responses
```

---

## 🧪 Running Tests

To run the automated test suite:

```bash
uv run pytest -v
```

Linting and code style checks:
```bash
uv run ruff check src tests
uv run ruff format --check src tests
```
