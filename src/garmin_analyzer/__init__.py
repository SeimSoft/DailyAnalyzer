"""GarminAnalyzer: Download and analyze recent Garmin activities, telemetry, GPS tracks, daily health stats, and photos."""

from garmin_analyzer.auth import GarminAuth
from garmin_analyzer.client import GarminAnalyzer
from garmin_analyzer.models import ActivityOverview, DailyHealthSummary, DownloadedActivity

__version__ = "0.1.0"

__all__ = [
    "ActivityOverview",
    "DailyHealthSummary",
    "DownloadedActivity",
    "GarminAnalyzer",
    "GarminAuth",
    "__version__",
]
