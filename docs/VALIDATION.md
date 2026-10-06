# Validating fetched weather against your weather station

Everything runs through two commands and a small admin-only API. Nothing needs the station
data to exist up front: the forecast snapshots start accumulating as soon as the scheduler runs.

## 1. Let snapshots accumulate
Every sync stores the forecast *as issued* (`ForecastSnapshot`), because the live forecast table is
overwritten on each sync. This is what lets you measure forecast error by lead time (day 1 ... day 7).

## 2. Import the station export (CSV or Excel)
    python manage.py import_station_data station.csv --station "Baramati AWS" --farm 1 --dry-run
    python manage.py import_station_data station.csv --station "Baramati AWS" --farm 1 \
        --wind-unit kmh --rain-mode cumulative --solar-unit wm2

* Columns are auto-detected; override with `--col-time/--col-temp/--col-rh/--col-rain/--col-wind/--col-solar`.
* Declare the file's real units and timezone (`--timezone`, `--temp-unit`, `--wind-unit`, `--rain-unit`,
  `--rain-mode interval|cumulative`, `--solar-unit wm2|mj|kwh`, `--month-first` for MM/DD dates, `--wind-height`).
* Use `--dry-run` first: it prints what was parsed and the detected units, and writes nothing.
* Re-importing the same file is safe (keyed on station + timestamp).
* A template is in `backend/validation/sample/station_template.csv`.

## 3. Run the validation
    python manage.py validate_weather --station "Baramati AWS" --start 2026-10-01 --end 2026-10-31

Writes `report.html` (scatter plots), `report.md`, `report.json`, `summary.csv`, `daily_pairs.csv`
and `station_daily.csv` per station into `validation_reports/` (in Docker: `/exchange`).
Error is always *fetched minus station*. Days with under 80% of the station's readings are skipped
(`--min-coverage`). Rain is scored both as daily totals and as rain / no-rain (`--rain-threshold`, default 1 mm).
Seeded demo rows (`data_source = seed`) are ignored, so demo data can never pass as validation.
Stored "actual" weather is scored separately per `data_source`: `actual:open_meteo_archive` (ERA5) and
`actual:open_meteo_recent` (the recent-days window the archive has not published yet). Rows stored by
earlier versions of the project appear under their original label, so old and new history are never mixed.

## 4. Read it honestly
* Use at least 30 days, ideally more than one season, before trusting any bias number.
* One station validates one place; farm-to-station distance is part of the error.
* Wind is not the same statistic everywhere: Open-Meteo *history* rows store the daily MEAN at 2 m (derived
  from hourly 10 m wind, scaled with FAO-56 Eq. 47), while *forecast* rows store the daily MAX at 10 m. The
  report compares each with the matching station statistic. The ET0 calculation uses the stored value as a
  2 m mean wind, so forecast ET0 tends to run high. Check the ET0 bias in your first report before deciding
  whether to change the forecast wind variable or add a height correction.
* Do not bias-correct until you have enough pairs; keep raw and corrected values separate.

## API (admin only)
`GET /api/validation/stations/` and `GET /api/validation/summary/?station=<id>&days=30`
