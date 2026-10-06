"""
Validation engine - turns raw station readings and stored model weather into
error statistics. Pure pandas/numpy: no Django models are touched here, so every
function can be unit-tested with plain DataFrames.

Conventions
-----------
* "model" = the weather the system fetched (Open-Meteo history / forecast rows, or a
  forecast snapshot); "station" = the physical weather station (ground truth).
* Every error is  model - station,  so a positive bias means the model reads high.
* Days are LOCAL calendar days of the station's timezone, which is how Open-Meteo
  (timezone=auto) reports its daily values.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# variable -> (label, unit)
VARIABLES = {
    "temp_max_c": ("Max temperature", "°C"),
    "temp_min_c": ("Min temperature", "°C"),
    "humidity_pct": ("Mean relative humidity", "%"),
    "rainfall_mm": ("Daily rainfall", "mm"),
    "solar_mj_m2": ("Solar radiation", "MJ/m²/day"),
    "wind_kmh": ("Wind speed", "km/h"),
    "et0_mm": ("Reference ET0 (FAO-56 PM)", "mm/day"),
}

# What the stored wind_kmh means for each data source (see weather_service.py).
WIND_DEFINITION = {
    # History rows: daily MEAN of hourly 10 m wind, scaled to 2 m (see weather_service).
    # Any source not listed here (including rows stored before the Open-Meteo-only
    # migration) is treated as a 2 m daily mean, which is what those rows hold.
    "open_meteo_archive": "mean_2m",
    "open_meteo_recent": "mean_2m",
    # Forecast rows: Open-Meteo wind_speed_10m_max, the daily max at 10 m.
    "open_meteo": "max_10m",
}

DEFAULT_RAIN_THRESHOLD_MM = 1.0
DEFAULT_MIN_COVERAGE = 0.8


# ---------------------------------------------------------------------------
# Unit helpers
# ---------------------------------------------------------------------------

def wind_height_factor(from_height_m: float, to_height_m: float) -> float:
    """Scale factor to move a wind speed between heights (FAO-56 Eq. 47 log profile)."""
    def _ln(z):
        return math.log(max(67.8 * z - 5.42, 1.0001))
    return _ln(to_height_m) / _ln(from_height_m)


# ---------------------------------------------------------------------------
# Station -> daily
# ---------------------------------------------------------------------------

def station_daily(
    readings: pd.DataFrame,
    tz: str = "Asia/Kolkata",
    wind_height_m: float = 2.0,
    min_coverage: float = DEFAULT_MIN_COVERAGE,
) -> pd.DataFrame:
    """
    Aggregate raw station readings to one row per local calendar day.

    `readings` needs a UTC-aware `timestamp` column plus any of: temp_c,
    humidity_pct, rain_mm (per interval), wind_ms, solar_wm2 (mean over interval).

    A variable on a day is kept only if its readings cover at least `min_coverage`
    of the day (judged against the station's median logging interval); otherwise it
    is NaN so incomplete days never distort the statistics.

    Returned columns: temp_max_c, temp_min_c, humidity_pct, rainfall_mm,
    solar_mj_m2, wind_mean_2m_kmh, wind_max_10m_kmh and a `coverage` column.
    """
    cols = ["temp_max_c", "temp_min_c", "humidity_pct", "rainfall_mm", "solar_mj_m2",
            "wind_mean_2m_kmh", "wind_max_10m_kmh", "coverage"]
    if readings is None or readings.empty:
        return pd.DataFrame(columns=cols, index=pd.DatetimeIndex([], name="date"))

    df = readings.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").drop_duplicates("timestamp")
    df["local"] = df["timestamp"].dt.tz_convert(tz)
    df["date"] = df["local"].dt.tz_localize(None).dt.normalize()
    for c in ("temp_c", "humidity_pct", "rain_mm", "wind_ms", "solar_wm2"):
        if c not in df.columns:
            df[c] = np.nan
        df[c] = pd.to_numeric(df[c], errors="coerce")

    step = df["timestamp"].diff().dt.total_seconds().median()
    if not step or math.isnan(step) or step <= 0:
        step = 3600.0
    expected = 86400.0 / step

    g = df.groupby("date")
    counts = g[["temp_c", "humidity_pct", "rain_mm", "wind_ms", "solar_wm2"]].count()
    ok = (counts / expected) >= min_coverage

    out = pd.DataFrame(index=g.size().index)
    out.index.name = "date"
    out["temp_max_c"] = g["temp_c"].max().where(ok["temp_c"])
    out["temp_min_c"] = g["temp_c"].min().where(ok["temp_c"])
    out["humidity_pct"] = g["humidity_pct"].mean().where(ok["humidity_pct"])
    out["rainfall_mm"] = g["rain_mm"].sum(min_count=1).where(ok["rain_mm"])
    # mean W/m2 over the day -> MJ/m2/day  (x 86400 s / 1e6)
    out["solar_mj_m2"] = (g["solar_wm2"].mean() * 0.0864).where(ok["solar_wm2"])

    to2 = wind_height_factor(wind_height_m, 2.0)
    to10 = wind_height_factor(wind_height_m, 10.0)
    out["wind_mean_2m_kmh"] = (g["wind_ms"].mean() * to2 * 3.6).where(ok["wind_ms"])
    # daily max of HOURLY means, to match how the model's daily max is defined
    hourly = df.set_index("local")["wind_ms"].resample("1h").mean().dropna()
    if len(hourly):
        hourly_max = hourly.groupby(hourly.index.tz_localize(None).normalize()).max()
        out["wind_max_10m_kmh"] = (hourly_max * to10 * 3.6).reindex(out.index).where(ok["wind_ms"])
    else:
        out["wind_max_10m_kmh"] = np.nan

    out["coverage"] = counts.max(axis=1) / expected
    out["coverage"] = out["coverage"].clip(upper=1.0)
    return out


def add_station_et0(daily: pd.DataFrame, latitude: float, elevation_m: float) -> pd.DataFrame:
    """Add `et0_mm` computed from station Tmax/Tmin/RH/wind(2 m)/solar with the project's own FAO-56 function."""
    from advisory.weather_service import compute_et0_penman_monteith

    d = daily.copy()
    et0 = []
    for date, r in d.iterrows():
        needed = [r.get("temp_max_c"), r.get("temp_min_c"), r.get("humidity_pct"),
                  r.get("wind_mean_2m_kmh"), r.get("solar_mj_m2")]
        if any(pd.isna(v) for v in needed):
            et0.append(np.nan)
            continue
        et0.append(compute_et0_penman_monteith(
            temp_max_c=float(r["temp_max_c"]), temp_min_c=float(r["temp_min_c"]),
            humidity_pct=float(r["humidity_pct"]), wind_kmh=float(r["wind_mean_2m_kmh"]),
            solar_mj_m2=float(r["solar_mj_m2"]), latitude_deg=latitude,
            elevation_m=elevation_m, day_of_year=pd.Timestamp(date).timetuple().tm_yday,
        ))
    d["et0_mm"] = et0
    return d


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def _clean(v):
    """numpy/NaN -> plain float or None so results serialise to JSON."""
    if v is None:
        return None
    v = float(v)
    return None if math.isnan(v) or math.isinf(v) else round(v, 4)


def continuous_metrics(model, station) -> dict:
    """n, bias (model - station), MAE, RMSE, Pearson r and R² over paired values."""
    m = pd.to_numeric(pd.Series(model), errors="coerce").to_numpy(dtype=float)
    s = pd.to_numeric(pd.Series(station), errors="coerce").to_numpy(dtype=float)
    mask = ~(np.isnan(m) | np.isnan(s))
    m, s = m[mask], s[mask]
    n = int(mask.sum())
    if n == 0:
        return {"n": 0, "bias": None, "mae": None, "rmse": None, "r": None, "r2": None,
                "mean_model": None, "mean_station": None}
    err = m - s
    r = None
    if n >= 3 and np.std(m) > 0 and np.std(s) > 0:
        r = float(np.corrcoef(m, s)[0, 1])
    return {
        "n": n,
        "bias": _clean(err.mean()),
        "mae": _clean(np.abs(err).mean()),
        "rmse": _clean(math.sqrt((err ** 2).mean())),
        "r": _clean(r),
        "r2": _clean(r * r) if r is not None else None,
        "mean_model": _clean(m.mean()),
        "mean_station": _clean(s.mean()),
    }


def rain_event_metrics(model, station, threshold_mm: float = DEFAULT_RAIN_THRESHOLD_MM) -> dict:
    """
    Rain / no-rain skill at `threshold_mm`: hits, misses, false alarms, correct
    negatives plus POD (hit rate), FAR (false-alarm ratio), CSI and accuracy.
    Rain is patchy in space, so judge it by these as well as by daily totals.
    """
    m = pd.to_numeric(pd.Series(model), errors="coerce").to_numpy(dtype=float)
    s = pd.to_numeric(pd.Series(station), errors="coerce").to_numpy(dtype=float)
    mask = ~(np.isnan(m) | np.isnan(s))
    m, s = m[mask] >= threshold_mm, s[mask] >= threshold_mm
    hits = int((m & s).sum())
    misses = int((~m & s).sum())
    false_alarms = int((m & ~s).sum())
    correct_neg = int((~m & ~s).sum())
    n = hits + misses + false_alarms + correct_neg

    def ratio(a, b):
        return _clean(a / b) if b else None

    return {
        "threshold_mm": threshold_mm, "n": n, "hits": hits, "misses": misses,
        "false_alarms": false_alarms, "correct_negatives": correct_neg,
        "pod": ratio(hits, hits + misses),
        "far": ratio(false_alarms, hits + false_alarms),
        "csi": ratio(hits, hits + misses + false_alarms),
        "accuracy": ratio(hits + correct_neg, n),
        "station_rain_days": hits + misses, "model_rain_days": hits + false_alarms,
    }


# ---------------------------------------------------------------------------
# Pairing + full run
# ---------------------------------------------------------------------------

def _station_column(variable: str, source: str | None) -> str:
    if variable == "wind_kmh":
        return "wind_max_10m_kmh" if WIND_DEFINITION.get(source or "") == "max_10m" else "wind_mean_2m_kmh"
    return variable


def pair_with_station(model_df: pd.DataFrame, station_df: pd.DataFrame, variables=None,
                      source_col: str | None = "data_source") -> pd.DataFrame:
    """
    Join model rows (index or `date` column = date) with station daily rows.
    Returns a long frame: date, [lead_days], source, variable, model, station, error.
    """
    variables = variables or list(VARIABLES)
    if model_df is None or model_df.empty or station_df is None or station_df.empty:
        return pd.DataFrame(columns=["date", "lead_days", "source", "variable", "model", "station", "error"])

    mdf = model_df.copy()
    mdf["date"] = pd.to_datetime(mdf["date"]).dt.normalize()
    sdf = station_df.copy()
    sdf.index = pd.to_datetime(sdf.index).normalize()

    rows = []
    for _, r in mdf.iterrows():
        d = r["date"]
        if d not in sdf.index:
            continue
        srow = sdf.loc[d]
        source = r.get(source_col) if source_col else None
        for var in variables:
            if var not in r or pd.isna(r[var]):
                continue
            sval = srow.get(_station_column(var, source))
            if sval is None or pd.isna(sval):
                continue
            rows.append({
                "date": d.date(), "lead_days": r.get("lead_days"), "source": source, "variable": var,
                "model": float(r[var]), "station": float(sval), "error": float(r[var]) - float(sval),
            })
    return pd.DataFrame(rows, columns=["date", "lead_days", "source", "variable", "model", "station", "error"])


@dataclass
class ValidationResult:
    actual: dict = field(default_factory=dict)            # {source: {variable: metrics}}
    actual_rain_events: dict = field(default_factory=dict)  # {source: rain metrics}
    forecast_by_lead: dict = field(default_factory=dict)  # {lead: {variable: metrics}}
    forecast_rain_events: dict = field(default_factory=dict)  # {lead: rain metrics}
    pairs_actual: pd.DataFrame = field(default_factory=pd.DataFrame)
    pairs_forecast: pd.DataFrame = field(default_factory=pd.DataFrame)
    station_days: int = 0
    notes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "station_days": self.station_days,
            "actual": self.actual,
            "actual_rain_events": self.actual_rain_events,
            "forecast_by_lead": {str(k): v for k, v in self.forecast_by_lead.items()},
            "forecast_rain_events": {str(k): v for k, v in self.forecast_rain_events.items()},
            "notes": self.notes,
        }


def _metrics_by_variable(pairs: pd.DataFrame) -> dict:
    out = {}
    for var, grp in pairs.groupby("variable"):
        out[var] = continuous_metrics(grp["model"], grp["station"])
    return out


def run_validation(actual_df: pd.DataFrame, snapshot_df: pd.DataFrame, station_df: pd.DataFrame,
                   rain_threshold_mm: float = DEFAULT_RAIN_THRESHOLD_MM) -> ValidationResult:
    """
    actual_df    stored 'actual' rows (columns: date, data_source + weather variables)
    snapshot_df  forecast snapshots (columns: target_date as `date`, lead_days, + variables)
    station_df   output of station_daily() (+ add_station_et0)
    """
    res = ValidationResult()
    res.station_days = int(len(station_df)) if station_df is not None else 0

    # Rows seeded as demo data are not real weather: never validate them.
    if actual_df is not None and not actual_df.empty and "data_source" in actual_df:
        n_seed = int((actual_df["data_source"] == "seed").sum())
        if n_seed:
            res.notes.append(f"{n_seed} seeded demo row(s) were ignored (data_source = 'seed').")
        actual_df = actual_df[actual_df["data_source"] != "seed"]

    res.pairs_actual = pair_with_station(actual_df, station_df)
    for source, grp in res.pairs_actual.groupby("source"):
        res.actual[source] = _metrics_by_variable(grp)
        rain = grp[grp["variable"] == "rainfall_mm"]
        if len(rain):
            res.actual_rain_events[source] = rain_event_metrics(rain["model"], rain["station"], rain_threshold_mm)

    if snapshot_df is not None and not snapshot_df.empty:
        snap = snapshot_df.copy()
        snap["data_source"] = snap.get("source", "open_meteo")
        res.pairs_forecast = pair_with_station(snap, station_df)
        # a forecast for a day is only judged once the station day is complete
        for lead, grp in res.pairs_forecast.groupby("lead_days"):
            lead = int(lead)
            res.forecast_by_lead[lead] = _metrics_by_variable(grp)
            rain = grp[grp["variable"] == "rainfall_mm"]
            if len(rain):
                res.forecast_rain_events[lead] = rain_event_metrics(rain["model"], rain["station"], rain_threshold_mm)

    res.notes.append(
        "Wind: Open-Meteo history rows hold the daily MEAN at 2 m (derived from hourly 10 m wind); "
        "Open-Meteo forecast rows hold the daily MAX at 10 m. "
        "Each is compared with the matching station statistic."
    )
    res.notes.append(
        "ET0 'station' is computed from the station's own Tmax/Tmin/RH/wind/solar with the project's "
        "FAO-56 Penman-Monteith function. Stored Open-Meteo ET0 is computed from the 10 m daily-MAX wind "
        "used as if it were a 2 m mean wind, which tends to bias it high; a positive ET0 bias is therefore likely."
    )
    return res
