"""
Compare the fetched weather with a station and write a report.

    python manage.py validate_weather                       # every station, all data
    python manage.py validate_weather --station "Baramati AWS" --start 2026-09-01 --end 2026-09-30
    python manage.py validate_weather --out-dir reports/sept --rain-threshold 2.5

Writes summary.csv, daily_pairs.csv, station_daily.csv, report.json, report.md and
report.html (open the HTML in a browser; it has scatter plots) per station.
"""

import datetime
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from validation import engine, reporting
from validation.models import WeatherStation
from validation.service import validate_station


def _date(value):
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        raise CommandError(f"'{value}' is not a YYYY-MM-DD date.")


class Command(BaseCommand):
    help = "Validate fetched weather against weather-station data and write a report."

    def add_arguments(self, parser):
        parser.add_argument("--station", help="Station name (default: all stations)")
        parser.add_argument("--start", type=_date)
        parser.add_argument("--end", type=_date)
        parser.add_argument("--min-coverage", type=float, default=engine.DEFAULT_MIN_COVERAGE,
                            help="Minimum share of a day's readings needed to use that day (default 0.8)")
        parser.add_argument("--rain-threshold", type=float, default=engine.DEFAULT_RAIN_THRESHOLD_MM,
                            help="mm/day at or above which a day counts as a rain day (default 1.0)")
        parser.add_argument("--out-dir", default="validation_reports")
        parser.add_argument("--formats", default="csv,json,md,html")

    def handle(self, *args, **o):
        stations = WeatherStation.objects.select_related("farm")
        if o["station"]:
            stations = stations.filter(name=o["station"])
        if not stations.exists():
            raise CommandError("No matching station. Import data first: manage.py import_station_data ...")

        formats = tuple(x.strip() for x in o["formats"].split(",") if x.strip())
        for station in stations:
            result, daily, context = validate_station(
                station, o["start"], o["end"], o["min_coverage"], o["rain_threshold"])
            slug = re.sub(r"[^A-Za-z0-9]+", "_", station.name).strip("_") or f"station_{station.pk}"
            folder = Path(o["out_dir"]) / slug
            written = reporting.write_reports(result, daily, context, folder, formats)
            self.stdout.write(self.style.SUCCESS(f"\n=== {station.name} -> {station.farm} ==="))
            self.stdout.write(reporting.to_markdown(result, context))
            self.stdout.write(f"Reports written to {folder}/ ({', '.join(p.name for p in written)})")
