"""
Parse a weather-station export (CSV / TSV / Excel) into normalised readings.

Stations log different things in different units, so this module
  1. finds the columns (auto-detected from common names, or given explicitly),
  2. converts everything to  deg C, %, mm per interval, m/s and W/m2,
  3. rejects physically impossible values (QC),
and reports exactly what it did so nothing is silently guessed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

TEMP_UNITS = {"c": lambda s: s, "f": lambda s: (s - 32.0) * 5.0 / 9.0, "k": lambda s: s - 273.15}
WIND_UNITS = {"ms": 1.0, "kmh": 1 / 3.6, "mph": 0.44704, "kn": 0.514444}
RAIN_UNITS = {"mm": 1.0, "in": 25.4}

# physical plausibility limits (values outside are discarded, not clipped)
QC_LIMITS = {
    "temp_c": (-20.0, 60.0),
    "humidity_pct": (0.0, 105.0),   # sensors often read 100-103; clipped to 100 below
    "rain_mm": (0.0, 200.0),        # per logging interval
    "wind_ms": (0.0, 75.0),
    "solar_wm2": (0.0, 1500.0),
}

FIELDS = ("temp_c", "humidity_pct", "rain_mm", "wind_ms", "solar_wm2")


class StationFileError(ValueError):
    pass


def _norm(name) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


# (include substrings, exclude substrings), first matching column wins
_DETECT = {
    "temp_c": (("temp",), ("dew", "indoor", "soil", "min", "max", "heat", "chill", "feel")),
    "humidity_pct": (("hum", "rh"), ("indoor", "abs", "soil")),
    "rain_mm": (("rain", "precip"), ("rate", "prob", "chance", "intensity")),
    "wind_ms": (("wind", "ws"), ("dir", "gust", "chill", "bearing", "max")),
    "solar_wm2": (("solar", "radiation", "srad", "irradiance", "ghi"), ("uv", "index")),
}
_TIME_EXACT = ("timestamp", "datetime", "datetimeist", "dateandtime", "logtime", "time", "date")


def detect_columns(columns) -> dict:
    """Guess which column holds what. Returns {'time': [...], field: name-or-None}."""
    normed = {c: _norm(c) for c in columns}
    found = {"time": []}

    # timestamp: one combined column, or separate date + time columns
    for key in ("timestamp", "datetime", "datetimeist", "dateandtime", "logtime"):
        for c, n in normed.items():
            if n == key:
                found["time"] = [c]
                break
        if found["time"]:
            break
    if not found["time"]:
        date_c = next((c for c, n in normed.items() if n == "date"), None)
        time_c = next((c for c, n in normed.items() if n == "time"), None)
        if date_c and time_c:
            found["time"] = [date_c, time_c]
        elif date_c or time_c:
            found["time"] = [date_c or time_c]

    taken = set(found["time"])
    for fld, (inc, exc) in _DETECT.items():
        pick = None
        for c, n in normed.items():
            if c in taken:
                continue
            if any(n.startswith(i) or (len(i) > 2 and i in n) for i in inc) and not any(e in n for e in exc):
                # 'rh' must be a token at the start to avoid matching e.g. 'rhythm'
                pick = c
                break
        found[fld] = pick
        if pick:
            taken.add(pick)
    return found


@dataclass
class ParsedStationData:
    readings: pd.DataFrame
    report: dict = field(default_factory=dict)


def _read_table(path: Path, skip_rows: int, sheet) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xlsm", ".xls"):
        return pd.read_excel(path, skiprows=skip_rows, sheet_name=sheet or 0)
    if suffix in (".csv", ".txt", ".tsv", ".dat"):
        return pd.read_csv(path, sep=None, engine="python", skiprows=skip_rows,
                           encoding_errors="replace", skipinitialspace=True)
    raise StationFileError(f"Unsupported file type '{suffix}'. Use .csv, .txt, .tsv or .xlsx.")


def parse_station_file(
    path,
    timezone: str = "Asia/Kolkata",
    columns: dict | None = None,
    temp_unit: str = "c",
    wind_unit: str = "ms",
    rain_unit: str = "mm",
    rain_mode: str = "interval",
    solar_unit: str = "wm2",
    dayfirst: bool = True,
    skip_rows: int = 0,
    sheet=None,
) -> ParsedStationData:
    """
    columns   optional explicit mapping, e.g. {"time": "Date Time", "temp_c": "Out Temp", ...}.
              Anything not given is auto-detected.
    rain_mode 'interval'   - each row is rain since the previous row (tipping bucket)
              'cumulative' - a running total that may reset (daily/monthly counter)
    solar_unit 'wm2' (mean power), 'mj' (MJ/m2 in the interval) or 'kwh' (kWh/m2 in the interval)
    """
    path = Path(path)
    if not path.exists():
        raise StationFileError(f"File not found: {path}")
    if temp_unit.lower() not in TEMP_UNITS:
        raise StationFileError(f"temp_unit must be one of {sorted(TEMP_UNITS)}")
    if wind_unit.lower() not in WIND_UNITS:
        raise StationFileError(f"wind_unit must be one of {sorted(WIND_UNITS)}")
    if rain_unit.lower() not in RAIN_UNITS:
        raise StationFileError(f"rain_unit must be one of {sorted(RAIN_UNITS)}")
    if rain_mode not in ("interval", "cumulative"):
        raise StationFileError("rain_mode must be 'interval' or 'cumulative'")
    if solar_unit not in ("wm2", "mj", "kwh"):
        raise StationFileError("solar_unit must be 'wm2', 'mj' or 'kwh'")

    raw = _read_table(path, skip_rows, sheet)
    raw.columns = [str(c).strip() for c in raw.columns]
    if raw.empty:
        raise StationFileError("The file has no data rows.")

    auto = detect_columns(list(raw.columns))
    mapping = {"time": auto["time"], **{f: auto[f] for f in FIELDS}}
    for key, value in (columns or {}).items():
        if value:
            if value not in raw.columns:
                raise StationFileError(f"Column '{value}' (for {key}) not found. Columns are: {list(raw.columns)}")
            mapping[key] = [value] if key == "time" else value
    if isinstance(mapping["time"], str):
        mapping["time"] = [mapping["time"]]
    if not mapping["time"]:
        raise StationFileError(f"Could not find a timestamp column. Columns are: {list(raw.columns)}. Pass it explicitly.")
    used = [f for f in FIELDS if mapping.get(f)]
    if not used:
        raise StationFileError(f"No weather columns recognised. Columns are: {list(raw.columns)}. Pass them explicitly.")

    # --- timestamp -> UTC ---------------------------------------------------
    if len(mapping["time"]) == 2:
        stamp = raw[mapping["time"][0]].astype(str).str.strip() + " " + raw[mapping["time"][1]].astype(str).str.strip()
    else:
        stamp = raw[mapping["time"][0]]
    ts = pd.to_datetime(stamp, dayfirst=dayfirst, errors="coerce", utc=False)
    if getattr(ts.dt, "tz", None) is not None:
        ts = ts.dt.tz_convert("UTC")
    else:
        ts = ts.dt.tz_localize(timezone, ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")

    df = pd.DataFrame({"timestamp": ts})
    for f in FIELDS:
        col = mapping.get(f)
        df[f] = pd.to_numeric(raw[col], errors="coerce") if col else np.nan

    n_read = len(df)
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp")
    n_bad_time = n_read - len(df)
    dup = int(df["timestamp"].duplicated().sum())
    df = df.drop_duplicates("timestamp", keep="last")

    # --- unit conversion ----------------------------------------------------
    df["temp_c"] = TEMP_UNITS[temp_unit.lower()](df["temp_c"])
    df["wind_ms"] = df["wind_ms"] * WIND_UNITS[wind_unit.lower()]
    df["rain_mm"] = df["rain_mm"] * RAIN_UNITS[rain_unit.lower()]

    if rain_mode == "cumulative" and df["rain_mm"].notna().any():
        diff = df["rain_mm"].diff()
        # a negative step means the counter was reset: the new value is the rain since the reset
        df["rain_mm"] = diff.where(diff >= 0, df["rain_mm"])
        df.iloc[0, df.columns.get_loc("rain_mm")] = np.nan  # no baseline for the first row

    if df["solar_wm2"].notna().any() and solar_unit != "wm2":
        step = df["timestamp"].diff().dt.total_seconds().median() or 3600.0
        energy_mj = df["solar_wm2"] if solar_unit == "mj" else df["solar_wm2"] * 3.6
        df["solar_wm2"] = energy_mj * 1e6 / step

    # --- QC -----------------------------------------------------------------
    qc = {}
    df["humidity_pct"] = df["humidity_pct"].where(~((df["humidity_pct"] > 100) & (df["humidity_pct"] <= 105)), 100.0)
    for f, (lo, hi) in QC_LIMITS.items():
        bad = df[f].notna() & ((df[f] < lo) | (df[f] > hi))
        qc[f] = int(bad.sum())
        df.loc[bad, f] = np.nan

    df = df.reset_index(drop=True)
    step = df["timestamp"].diff().dt.total_seconds().median() if len(df) > 1 else None
    report = {
        "file": path.name,
        "rows_read": int(n_read),
        "rows_kept": int(len(df)),
        "rows_bad_timestamp": int(n_bad_time),
        "duplicate_timestamps": dup,
        "columns_used": {k: v for k, v in mapping.items() if v},
        "columns_not_found": [f for f in FIELDS if not mapping.get(f)],
        "qc_rejected_values": qc,
        "first_reading_utc": df["timestamp"].min().isoformat() if len(df) else None,
        "last_reading_utc": df["timestamp"].max().isoformat() if len(df) else None,
        "median_interval_minutes": round(step / 60.0, 2) if step else None,
        "units": {"temp": temp_unit, "wind": wind_unit, "rain": f"{rain_unit}/{rain_mode}", "solar": solar_unit},
        "timezone": timezone,
    }
    if step and step > 3600 * 1.5:
        report["warning"] = (
            "Readings are less frequent than hourly. Daily max/min temperature and rain-day checks "
            "need hourly or finer data to be reliable."
        )
    return ParsedStationData(readings=df, report=report)
