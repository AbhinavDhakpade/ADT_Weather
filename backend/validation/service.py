"""Glue between the Django models and the pure engine."""

from __future__ import annotations

import datetime

import pandas as pd

from advisory.models import ActualWeatherReading

from . import engine
from .models import ForecastSnapshot, StationReading

ACTUAL_FIELDS = ["date", "data_source", "temp_max_c", "temp_min_c", "humidity_pct",
                 "rainfall_mm", "solar_mj_m2", "wind_kmh", "et0_mm"]
SNAPSHOT_FIELDS = ["target_date", "lead_days", "source", "temp_max_c", "temp_min_c", "humidity_pct",
                   "rainfall_mm", "solar_mj_m2", "wind_kmh", "et0_mm"]


def load_station_readings(station, start: datetime.date | None = None, end: datetime.date | None = None) -> pd.DataFrame:
    qs = StationReading.objects.filter(station=station)
    if start:
        qs = qs.filter(timestamp__date__gte=start - datetime.timedelta(days=1))
    if end:
        qs = qs.filter(timestamp__date__lte=end + datetime.timedelta(days=1))
    rows = qs.values("timestamp", "temp_c", "humidity_pct", "rain_mm", "wind_ms", "solar_wm2")
    return pd.DataFrame.from_records(rows)


def validate_station(
    station,
    start: datetime.date | None = None,
    end: datetime.date | None = None,
    min_coverage: float = engine.DEFAULT_MIN_COVERAGE,
    rain_threshold_mm: float = engine.DEFAULT_RAIN_THRESHOLD_MM,
):
    """
    Compare one station with its farm's stored weather.
    Returns (ValidationResult, station_daily_df, context dict).
    """
    farm = station.farm
    readings = load_station_readings(station, start, end)
    daily = engine.station_daily(readings, tz=station.timezone, wind_height_m=station.wind_height_m,
                                 min_coverage=min_coverage)
    if len(daily):
        idx = pd.to_datetime(daily.index)
        mask = pd.Series(True, index=daily.index)
        if start:
            mask &= idx >= pd.Timestamp(start)
        if end:
            mask &= idx <= pd.Timestamp(end)
        daily = daily[mask.to_numpy()]

    lat = station.latitude if station.latitude is not None else farm.latitude
    elev = station.elevation_m if station.elevation_m is not None else farm.elevation_m
    daily = engine.add_station_et0(daily, lat, elev) if len(daily) else daily

    actual_qs = ActualWeatherReading.objects.filter(farm=farm)
    snap_qs = ForecastSnapshot.objects.filter(farm=farm)
    if start:
        actual_qs, snap_qs = actual_qs.filter(date__gte=start), snap_qs.filter(target_date__gte=start)
    if end:
        actual_qs, snap_qs = actual_qs.filter(date__lte=end), snap_qs.filter(target_date__lte=end)
    actual_df = pd.DataFrame.from_records(actual_qs.values(*ACTUAL_FIELDS))
    snap_df = pd.DataFrame.from_records(snap_qs.values(*SNAPSHOT_FIELDS))
    if len(snap_df):
        snap_df = snap_df.rename(columns={"target_date": "date"})

    result = engine.run_validation(actual_df, snap_df, daily, rain_threshold_mm=rain_threshold_mm)

    distance_km = None
    if station.latitude is not None and station.longitude is not None:
        distance_km = round(_haversine_km(station.latitude, station.longitude, farm.latitude, farm.longitude), 2)
    context = {
        "station": station.name,
        "farm": farm.farm_name,
        "farm_latitude": farm.latitude,
        "farm_longitude": farm.longitude,
        "station_to_farm_km": distance_km,
        "elevation_diff_m": (round(station.elevation_m - farm.elevation_m, 1)
                             if station.elevation_m is not None else None),
        "start": str(start) if start else None,
        "end": str(end) if end else None,
        "min_coverage": min_coverage,
        "rain_threshold_mm": rain_threshold_mm,
        "valid_station_days": int(len(daily)),
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    }
    if len(daily) < 30:
        result.notes.append(
            f"Only {len(daily)} usable station day(s). Treat these statistics as indicative; "
            "30+ days (ideally across wet and dry weather) is needed before trusting or correcting any bias."
        )
    return result, daily, context


def _haversine_km(lat1, lon1, lat2, lon2):
    from math import asin, cos, radians, sin, sqrt
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 6371.0 * 2 * asin(sqrt(a))
