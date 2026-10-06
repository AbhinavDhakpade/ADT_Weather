"""
Import a weather-station export into the database.

    python manage.py import_station_data station.csv --station "Baramati AWS" --farm 1
    python manage.py import_station_data log.xlsx --station "Farm AWS" --farm 3 \
        --wind-unit kmh --rain-mode cumulative --solar-unit wm2 \
        --col-time "Date Time" --col-temp "Out Temp" --col-rh "Out Hum"

Columns are auto-detected from common names; every --col-* flag overrides one.
Re-running with the same file is safe: readings are keyed on (station, timestamp).
"""

import json

from django.core.management.base import BaseCommand, CommandError

from advisory.models import FarmProfile
from validation.models import StationReading, WeatherStation
from validation.station_import import StationFileError, parse_station_file

CHUNK = 2000


class Command(BaseCommand):
    help = "Import weather-station readings (CSV/Excel) for validating fetched weather."

    def add_arguments(self, parser):
        parser.add_argument("file")
        parser.add_argument("--station", required=True, help="Station name (created on first use)")
        parser.add_argument("--farm", type=int, help="Farm id this station validates (required for a new station)")
        parser.add_argument("--timezone", default=None, help="IANA tz of the file's timestamps (default: station's, else Asia/Kolkata)")
        parser.add_argument("--latitude", type=float)
        parser.add_argument("--longitude", type=float)
        parser.add_argument("--elevation", type=float, help="Station elevation, metres")
        parser.add_argument("--wind-height", type=float, help="Anemometer height, metres (default 2)")
        parser.add_argument("--temp-unit", default="c", choices=["c", "f", "k"])
        parser.add_argument("--wind-unit", default="ms", choices=["ms", "kmh", "mph", "kn"])
        parser.add_argument("--rain-unit", default="mm", choices=["mm", "in"])
        parser.add_argument("--rain-mode", default="interval", choices=["interval", "cumulative"])
        parser.add_argument("--solar-unit", default="wm2", choices=["wm2", "mj", "kwh"])
        parser.add_argument("--month-first", action="store_true", help="Dates are MM/DD/YYYY (default is DD/MM/YYYY)")
        parser.add_argument("--skip-rows", type=int, default=0)
        parser.add_argument("--sheet", default=None, help="Excel sheet name or index")
        for key in ("time", "temp", "rh", "rain", "wind", "solar"):
            parser.add_argument(f"--col-{key}", default=None, help=f"Column holding {key}")
        parser.add_argument("--dry-run", action="store_true", help="Parse and report, write nothing")

    def handle(self, *args, **o):
        station = WeatherStation.objects.filter(name=o["station"]).first()
        if station is None:
            if not o["farm"]:
                raise CommandError("New station: pass --farm <id> to say which farm it validates.")
            try:
                farm = FarmProfile.objects.get(pk=o["farm"])
            except FarmProfile.DoesNotExist:
                raise CommandError(f"Farm {o['farm']} does not exist.")
            station = WeatherStation(name=o["station"], farm=farm)
        elif o["farm"] and station.farm_id != o["farm"]:
            raise CommandError(f"Station '{station.name}' already validates farm {station.farm_id}, not {o['farm']}.")

        for attr, key in (("latitude", "latitude"), ("longitude", "longitude"),
                          ("elevation_m", "elevation"), ("wind_height_m", "wind_height")):
            if o[key] is not None:
                setattr(station, attr, o[key])
        if o["timezone"]:
            station.timezone = o["timezone"]

        columns = {"time": o["col_time"], "temp_c": o["col_temp"], "humidity_pct": o["col_rh"],
                   "rain_mm": o["col_rain"], "wind_ms": o["col_wind"], "solar_wm2": o["col_solar"]}
        sheet = o["sheet"]
        if sheet is not None and sheet.isdigit():
            sheet = int(sheet)
        try:
            parsed = parse_station_file(
                o["file"], timezone=station.timezone, columns=columns, temp_unit=o["temp_unit"],
                wind_unit=o["wind_unit"], rain_unit=o["rain_unit"], rain_mode=o["rain_mode"],
                solar_unit=o["solar_unit"], dayfirst=not o["month_first"], skip_rows=o["skip_rows"], sheet=sheet,
            )
        except StationFileError as exc:
            raise CommandError(str(exc))

        self.stdout.write(json.dumps(parsed.report, indent=2))
        if parsed.report["columns_not_found"]:
            self.stdout.write(self.style.WARNING(
                "Not found (will be skipped in validation): " + ", ".join(parsed.report["columns_not_found"])))
        if parsed.report.get("warning"):
            self.stdout.write(self.style.WARNING(parsed.report["warning"]))
        if o["dry_run"]:
            self.stdout.write(self.style.SUCCESS("Dry run: nothing written."))
            return

        station.save()
        df = parsed.readings
        fields = ["temp_c", "humidity_pct", "rain_mm", "wind_ms", "solar_wm2"]
        records = []
        for r in df.itertuples(index=False):
            records.append(StationReading(
                station=station, timestamp=r.timestamp.to_pydatetime(),
                **{f: (None if getattr(r, f) != getattr(r, f) else float(getattr(r, f))) for f in fields},
            ))
        for i in range(0, len(records), CHUNK):
            StationReading.objects.bulk_create(
                records[i:i + CHUNK], update_conflicts=True,
                unique_fields=["station", "timestamp"], update_fields=fields,
            )
        self.stdout.write(self.style.SUCCESS(
            f"Imported {len(records)} readings for station '{station.name}' (farm: {station.farm})."))
