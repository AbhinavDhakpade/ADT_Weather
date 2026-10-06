"""
weather_service.py

Live weather data layer for AgriAura. Open-Meteo is the ONLY external weather provider.

Three Open-Meteo requests cover everything, each used for what it is good at:
  - Historical Weather API (ERA5 reanalysis)  -> observed daily history older than
        ~5 days (``source = "open_meteo_archive"``).
  - Forecast API with ``past_days``            -> the recent days the archive has not
        published yet (``source = "open_meteo_recent"``), so the Actual Weather
        Database has no gap up to yesterday.
  - Forecast API                               -> today + 7-day forecast.

All three return raw meteorological variables only (temperature, humidity, rainfall,
solar radiation, wind). Per AgriAura's architecture, ET0 (FAO-56 Penman-Monteith,
simplified Hargreaves form), VPD (Tetens equation), and GDD (sugarcane
growing-degree-days) are always computed deterministically from those raw values in
this module — never fetched from an external source and never estimated by an ML
model.

Everything outside this module sees only the normalized ``RawDailyWeather`` object,
never Open-Meteo's raw response format.

Wind definition (important for ET0, which wants wind at 2 m):
  - history rows : daily MEAN of hourly 10 m wind, scaled to 2 m (FAO-56 Eq. 47).
  - forecast rows: daily MAX at 10 m (unchanged from before the provider migration).

Configuration (all optional; no API key is needed for these endpoints):
  OPEN_METEO_FORECAST_URL, OPEN_METEO_ARCHIVE_URL, OPEN_METEO_TIMEOUT_SECONDS
"""

from __future__ import annotations

import datetime
import logging
import math
import os
from dataclasses import dataclass

import requests

logger = logging.getLogger("advisory.weather")

# An empty value (e.g. passed through docker-compose as "") counts as "not set".
OPEN_METEO_URL = os.environ.get("OPEN_METEO_FORECAST_URL") or "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_ARCHIVE_URL = (
    os.environ.get("OPEN_METEO_ARCHIVE_URL") or "https://archive-api.open-meteo.com/v1/archive"
)

REQUEST_TIMEOUT = float(os.environ.get("OPEN_METEO_TIMEOUT_SECONDS") or "15")  # seconds

# ERA5 reaches the archive API with a delay of about 5 days; anything newer comes
# from the forecast API's `past_days` window instead.
ARCHIVE_LAG_DAYS = 5
MAX_PAST_DAYS = 92  # Open-Meteo's limit for `past_days`

SOURCE_ARCHIVE = "open_meteo_archive"
SOURCE_RECENT = "open_meteo_recent"
SOURCE_FORECAST = "open_meteo"

# FAO-56 Eq. 47: u2 = u_z * 4.87 / ln(67.8*z - 5.42); for z = 10 m this is ~0.748.
WIND_10M_TO_2M = 4.87 / math.log(67.8 * 10 - 5.42)

# Defaults used only when Open-Meteo returns null for a value (kept from the
# previous provider so downstream ET0/VPD maths never receives None).
DEFAULT_HUMIDITY_PCT = 70.0
DEFAULT_SOLAR_MJ_M2 = 18.0
DEFAULT_WIND_KMH = 10.8


@dataclass
class RawDailyWeather:
    date: datetime.date
    temp_max_c: float
    temp_min_c: float
    humidity_pct: float
    rainfall_mm: float
    solar_mj_m2: float
    wind_kmh: float
    weather_code: int | None = None
    wind_direction_deg: float | None = None
    wind_gusts_kmh: float | None = None
    uv_index_max: float | None = None
    precipitation_probability_pct: float | None = None
    sunrise: str | None = None  # "HH:MM" local time string, parsed by caller
    sunset: str | None = None
    source: str | None = None  # SOURCE_* constant; stored as data_source by the caller


class WeatherServiceError(Exception):
    pass


# ---------------------------------------------------------------------------
# Shared Open-Meteo plumbing
# ---------------------------------------------------------------------------

def _validate_coordinates(lat: float, lon: float) -> None:
    try:
        ok = -90.0 <= float(lat) <= 90.0 and -180.0 <= float(lon) <= 180.0
    except (TypeError, ValueError):
        ok = False
    if not ok:
        raise WeatherServiceError(f"Invalid coordinates for Open-Meteo: lat={lat!r}, lon={lon!r}")


def _get_json(url: str, params: dict, what: str) -> dict:
    """GET + JSON decode with uniform error handling. Raises WeatherServiceError."""
    try:
        resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        raise WeatherServiceError(f"Open-Meteo {what} request failed: {exc}") from exc

    if resp.status_code >= 400:
        # Open-Meteo explains 4xx errors as {"error": true, "reason": "..."}.
        reason = ""
        try:
            reason = resp.json().get("reason", "")
        except ValueError:
            pass
        raise WeatherServiceError(f"Open-Meteo {what} request failed: HTTP {resp.status_code} {reason}".strip())

    try:
        data = resp.json()
    except ValueError as exc:
        raise WeatherServiceError(f"Open-Meteo {what} returned invalid JSON: {exc}") from exc

    if isinstance(data, dict) and data.get("error"):
        raise WeatherServiceError(f"Open-Meteo {what} error: {data.get('reason', 'unknown')}")
    return data


def _num(v):
    """Open-Meteo uses null for missing values; also guard against NaN."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def _hourly_daily_means(hourly: dict, key: str) -> dict[str, float]:
    """
    {"YYYY-MM-DD": mean of that day's non-null hourly values} for hourly[key].
    The hourly timestamps are local time ("timezone=auto"), so the date prefix is
    the farm's local day.
    """
    times = hourly.get("time") or []
    values = hourly.get(key) or []
    buckets: dict[str, list[float]] = {}
    for t, v in zip(times, values):
        f = _num(v)
        if f is not None:
            buckets.setdefault(t[:10], []).append(f)
    return {day: sum(vals) / len(vals) for day, vals in buckets.items()}


def _history_from_response(data: dict, start: datetime.date, end: datetime.date, source: str) -> list[RawDailyWeather]:
    """Normalize an Open-Meteo daily+hourly response into RawDailyWeather rows in [start, end]."""
    try:
        daily = data["daily"]
        days = daily["time"]
    except (KeyError, TypeError) as exc:
        raise WeatherServiceError(f"Unexpected Open-Meteo response shape: {str(data)[:200]}") from exc

    n = len(days)
    for key in ("temperature_2m_max", "temperature_2m_min", "precipitation_sum", "shortwave_radiation_sum"):
        if len(daily.get(key) or []) != n:
            raise WeatherServiceError(f"Open-Meteo response is missing or has a short '{key}' column")

    hourly = data.get("hourly") or {}
    humidity_by_day = _hourly_daily_means(hourly, "relative_humidity_2m")
    wind10_by_day = _hourly_daily_means(hourly, "wind_speed_10m")  # km/h

    results: list[RawDailyWeather] = []
    for i, day_str in enumerate(days):
        day = datetime.date.fromisoformat(day_str)
        if day < start or day > end:
            continue
        tmax = _num(daily["temperature_2m_max"][i])
        tmin = _num(daily["temperature_2m_min"][i])
        if tmax is None or tmin is None:  # unusable day (same rule as before)
            continue

        humidity = humidity_by_day.get(day_str)
        solar = _num(daily["shortwave_radiation_sum"][i])
        wind10 = wind10_by_day.get(day_str)
        precip = _num(daily["precipitation_sum"][i])

        results.append(
            RawDailyWeather(
                date=day,
                temp_max_c=tmax,
                temp_min_c=tmin,
                humidity_pct=round(humidity, 1) if humidity is not None else DEFAULT_HUMIDITY_PCT,
                rainfall_mm=max(0.0, precip or 0.0),
                solar_mj_m2=solar if solar else DEFAULT_SOLAR_MJ_M2,
                # daily mean 10 m wind (km/h) -> 2 m, the height FAO-56 ET0 expects
                wind_kmh=round(wind10 * WIND_10M_TO_2M, 1) if wind10 is not None else DEFAULT_WIND_KMH,
                source=source,
            )
        )
    return results


_HISTORY_DAILY = "temperature_2m_max,temperature_2m_min,precipitation_sum,shortwave_radiation_sum"
_HISTORY_HOURLY = "relative_humidity_2m,wind_speed_10m"


# ---------------------------------------------------------------------------
# Open-Meteo — recent history (feeds the Actual Weather Database)
# ---------------------------------------------------------------------------

def fetch_open_meteo_history(lat: float, lon: float, days: int = 7) -> list[RawDailyWeather]:
    """
    Fetch the `days` daily readings ending YESTERDAY (today belongs to the forecast).

    Dates older than ARCHIVE_LAG_DAYS come from the Historical Weather API (ERA5);
    the newer ones, which the archive has not published yet, come from the Forecast
    API's `past_days` window. Each row records which one it came from in `.source`.

    Raises WeatherServiceError only if every needed request fails; if one of the two
    requests fails the other's rows are still returned (and the failure is logged).
    """
    _validate_coordinates(lat, lon)
    days = max(1, min(int(days), MAX_PAST_DAYS))

    today = datetime.date.today()
    end = today - datetime.timedelta(days=1)
    start = end - datetime.timedelta(days=days - 1)
    archive_end = min(end, today - datetime.timedelta(days=ARCHIVE_LAG_DAYS))

    results: list[RawDailyWeather] = []
    errors: list[WeatherServiceError] = []
    requested = 0

    if start <= archive_end:
        requested += 1
        params = {
            "latitude": lat, "longitude": lon,
            "start_date": start.isoformat(), "end_date": archive_end.isoformat(),
            "daily": _HISTORY_DAILY, "hourly": _HISTORY_HOURLY,
            "wind_speed_unit": "kmh", "timezone": "auto",
        }
        try:
            data = _get_json(OPEN_METEO_ARCHIVE_URL, params, "historical (archive)")
            results += _history_from_response(data, start, archive_end, SOURCE_ARCHIVE)
        except WeatherServiceError as exc:
            logger.warning("Open-Meteo archive fetch failed for (%s, %s): %s", lat, lon, exc)
            errors.append(exc)

    recent_start = max(start, archive_end + datetime.timedelta(days=1))
    if recent_start <= end:
        requested += 1
        past_days = (today - recent_start).days
        params = {
            "latitude": lat, "longitude": lon,
            "past_days": past_days, "forecast_days": 1,
            "daily": _HISTORY_DAILY, "hourly": _HISTORY_HOURLY,
            "wind_speed_unit": "kmh", "timezone": "auto",
        }
        try:
            data = _get_json(OPEN_METEO_URL, params, "recent-history (past_days)")
            results += _history_from_response(data, recent_start, end, SOURCE_RECENT)
        except WeatherServiceError as exc:
            logger.warning("Open-Meteo recent-history fetch failed for (%s, %s): %s", lat, lon, exc)
            errors.append(exc)

    if requested and len(errors) == requested:
        raise errors[0]
    results.sort(key=lambda r: r.date)
    return results


# ---------------------------------------------------------------------------
# Open-Meteo — today + forecast
# ---------------------------------------------------------------------------

def fetch_open_meteo_forecast(lat: float, lon: float, days: int = 7) -> list[RawDailyWeather]:
    """
    Fetch today + the next `days` of daily forecast from Open-Meteo for the given
    coordinates. No API key required.
    """
    _validate_coordinates(lat, lon)
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": ",".join(
            [
                "temperature_2m_max",
                "temperature_2m_min",
                "relative_humidity_2m_mean",
                "precipitation_sum",
                "precipitation_probability_max",
                "shortwave_radiation_sum",
                "wind_speed_10m_max",
                "wind_gusts_10m_max",
                "wind_direction_10m_dominant",
                "uv_index_max",
                "sunrise",
                "sunset",
                "weather_code",
            ]
        ),
        "forecast_days": days,
        "timezone": "auto",
    }

    data = _get_json(OPEN_METEO_URL, params, "forecast")

    try:
        daily = data["daily"]
    except KeyError as exc:
        raise WeatherServiceError(f"Unexpected Open-Meteo response shape: {data}") from exc

    n = len(daily["time"])

    def col(key, default=None):
        """Safe column getter — some fields may be absent for certain locations/models."""
        return daily.get(key, [default] * n)

    results: list[RawDailyWeather] = []
    for i, day_str in enumerate(daily["time"]):
        sunrise_raw = col("sunrise")[i]
        sunset_raw = col("sunset")[i]
        results.append(
            RawDailyWeather(
                date=datetime.date.fromisoformat(day_str),
                temp_max_c=daily["temperature_2m_max"][i],
                temp_min_c=daily["temperature_2m_min"][i],
                humidity_pct=col("relative_humidity_2m_mean", 70.0)[i] or 70.0,
                rainfall_mm=daily["precipitation_sum"][i] or 0.0,
                solar_mj_m2=col("shortwave_radiation_sum", 18.0)[i] or 18.0,
                wind_kmh=daily["wind_speed_10m_max"][i] or 10.0,
                weather_code=col("weather_code")[i],
                wind_direction_deg=col("wind_direction_10m_dominant")[i],
                wind_gusts_kmh=col("wind_gusts_10m_max")[i],
                uv_index_max=col("uv_index_max")[i],
                precipitation_probability_pct=col("precipitation_probability_max")[i],
                # sunrise/sunset come back as full ISO datetimes e.g. "2026-07-01T05:48";
                # keep just the "HH:MM" portion for storage/display
                sunrise=sunrise_raw.split("T")[1] if sunrise_raw and "T" in sunrise_raw else sunrise_raw,
                sunset=sunset_raw.split("T")[1] if sunset_raw and "T" in sunset_raw else sunset_raw,
                source=SOURCE_FORECAST,
            )
        )
    return results


WEATHER_CODE_ICON = {
    0: "☀️", 1: "🌤️", 2: "⛅", 3: "☁️",
    45: "🌫️", 48: "🌫️",
    51: "🌦️", 53: "🌦️", 55: "🌦️",
    61: "🌧️", 63: "🌧️", 65: "🌧️",
    71: "🌨️", 73: "🌨️", 75: "🌨️",
    80: "🌦️", 81: "🌧️", 82: "🌧️",
    95: "⛈️", 96: "⛈️", 99: "⛈️",
}

WEATHER_CODE_TEXT = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
    80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Severe thunderstorm with hail",
}

COMPASS_POINTS = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
]


def icon_for_weather_code(code: int | None) -> str:
    if code is None:
        return "⛅"
    return WEATHER_CODE_ICON.get(code, "⛅")


def text_for_weather_code(code: int | None) -> str:
    if code is None:
        return "Partly cloudy"
    return WEATHER_CODE_TEXT.get(code, "Partly cloudy")


def compass_direction(degrees: float | None) -> str | None:
    """Convert a wind direction in degrees to a 16-point compass label."""
    if degrees is None:
        return None
    idx = round(degrees / 22.5) % 16
    return COMPASS_POINTS[idx]


# ---------------------------------------------------------------------------
# Deterministic agronomy physics — ET0, VPD, GDD
# ---------------------------------------------------------------------------

def saturation_vapour_pressure_kpa(temp_c: float) -> float:
    """Tetens equation."""
    return 0.6108 * math.exp((17.27 * temp_c) / (temp_c + 237.3))


def compute_vpd_kpa(temp_max_c: float, temp_min_c: float, humidity_pct: float) -> float:
    """
    Vapour Pressure Deficit using the Tetens equation, FAO-56 style:
    es = mean of es(Tmax) and es(Tmin); ea = es * (RH/100); VPD = es - ea.
    """
    es_max = saturation_vapour_pressure_kpa(temp_max_c)
    es_min = saturation_vapour_pressure_kpa(temp_min_c)
    es = (es_max + es_min) / 2
    ea = es * (humidity_pct / 100.0)
    return round(max(0.0, es - ea), 2)


def compute_et0_hargreaves_mm(temp_max_c: float, temp_min_c: float, solar_mj_m2: float) -> float:
    """
    Simplified Hargreaves-Samani ET0 estimate (mm/day), using measured/estimated
    solar radiation rather than extraterrestrial radiation tables, since both data
    sources already provide solar radiation directly.

    ET0 = 0.0023 * Ra_equivalent * (Tmean + 17.8) * sqrt(Tmax - Tmin)

    Ra_equivalent here uses the provided shortwave radiation (MJ/m2/day) converted
    to mm/day equivalent (1 MJ/m2 ~= 0.408 mm evaporation equivalent), which is the
    standard FAO-56 conversion factor.
    """
    temp_mean = (temp_max_c + temp_min_c) / 2
    temp_range = max(0.1, temp_max_c - temp_min_c)
    ra_mm_equiv = solar_mj_m2 * 0.408
    et0 = 0.0023 * ra_mm_equiv * (temp_mean + 17.8) * math.sqrt(temp_range)
    return round(max(0.0, et0), 2)


def compute_et0_penman_monteith(
    temp_max_c: float,
    temp_min_c: float,
    humidity_pct: float,
    wind_kmh: float,
    solar_mj_m2: float,
    latitude_deg: float,
    elevation_m: float = 560.0,
    day_of_year: int = 196,
    rh_max: float | None = None,
    rh_min: float | None = None,
) -> float:
    """FAO-56 Penman-Monteith reference evapotranspiration ET0 (mm/day).

    Implements the method described in ET_and_Kc.docx (Allen et al., 1998,
    FAO-56 Ch. 2) using the AWS inputs Tmax, Tmin, RH, wind and solar radiation.
    Reproduces the document's worked example (34/22 C, RH 90/50, u2 2.5 m/s,
    Rs 22 MJ, z 560 m, lat 18.18, DOY 196) -> 5.46 mm/day.

    Production data carries a single mean RH, so actual vapour pressure ea is
    taken via FAO Eq. 19 (ea = es * RHmean/100). If rh_max and rh_min are both
    supplied, FAO Eq. 17 is used instead (as in the document).
    """
    tmean = (temp_max_c + temp_min_c) / 2.0

    # Step 1.1 saturation vapour pressure
    es_tmax = saturation_vapour_pressure_kpa(temp_max_c)
    es_tmin = saturation_vapour_pressure_kpa(temp_min_c)
    es = (es_tmax + es_tmin) / 2.0

    # Step 1.2 actual vapour pressure
    if rh_max is not None and rh_min is not None:
        ea = (es_tmin * rh_max + es_tmax * rh_min) / 200.0
    else:
        ea = es * (humidity_pct / 100.0)

    # Step 1.4 slope of the vapour pressure curve (Delta)
    es_tmean = saturation_vapour_pressure_kpa(tmean)
    delta = (4098.0 * es_tmean) / ((tmean + 237.3) ** 2)

    # Steps 1.5-1.6 atmospheric pressure + psychrometric constant
    pressure = 101.3 * (((293.0 - 0.0065 * elevation_m) / 293.0) ** 5.26)
    gamma = 0.000665 * pressure

    # Step 1.7 extraterrestrial radiation Ra (FAO Eq. 21-25)
    phi = math.radians(latitude_deg)
    dr = 1.0 + 0.033 * math.cos((2.0 * math.pi * day_of_year) / 365.0)
    decl = 0.409 * math.sin((2.0 * math.pi * day_of_year) / 365.0 - 1.39)
    # clamp for high latitudes where the sun may not set/rise
    x = max(-1.0, min(1.0, -math.tan(phi) * math.tan(decl)))
    omega_s = math.acos(x)
    gsc = 0.0820
    ra = ((24.0 * 60.0) / math.pi) * gsc * dr * (
        omega_s * math.sin(phi) * math.sin(decl)
        + math.cos(phi) * math.cos(decl) * math.sin(omega_s)
    )

    # Step 1.8-1.11 net radiation Rn
    rso = (0.75 + 2e-5 * elevation_m) * ra
    rns = (1.0 - 0.23) * solar_mj_m2
    rs_rso = min(1.0, solar_mj_m2 / rso) if rso > 0 else 0.9
    sigma = 4.903e-9
    tmax_k = temp_max_c + 273.16
    tmin_k = temp_min_c + 273.16
    rnl = (
        sigma
        * ((tmax_k ** 4 + tmin_k ** 4) / 2.0)
        * (0.34 - 0.14 * math.sqrt(max(0.0, ea)))
        * (1.35 * rs_rso - 0.35)
    )
    rn = rns - rnl

    # Step 1.12-1.13 soil heat flux (0 for daily) + ET0
    g = 0.0
    u2 = wind_kmh / 3.6  # km/h -> m/s
    numerator = 0.408 * delta * (rn - g) + gamma * (900.0 / (tmean + 273.0)) * u2 * (es - ea)
    denominator = delta + gamma * (1.0 + 0.34 * u2)
    et0 = numerator / denominator if denominator else 0.0
    return round(max(0.0, et0), 2)


def compute_gdd(temp_max_c: float, temp_min_c: float, base_temp_c: float) -> float:
    """Standard growing-degree-days: mean temp minus base, floored at zero."""
    temp_mean = (temp_max_c + temp_min_c) / 2
    return round(max(0.0, temp_mean - base_temp_c), 1)


def crop_stage_for_gdd(gdd_cumulative: float, growth_stages) -> str:
    """Resolve the current growth-stage name from cumulative GDD.

    growth_stages is an iterable of objects/dicts with .stage_name / .gdd_threshold
    (or ["stage_name"] / ["gdd_threshold"]) ordered by ascending threshold — the
    same CropGrowthStage rows seeded for a farm. Returns the highest stage whose
    threshold has been reached; defaults to "Sprouting" if none match.
    """
    def _name(s):
        return s["stage_name"] if isinstance(s, dict) else s.stage_name

    def _threshold(s):
        return s["gdd_threshold"] if isinstance(s, dict) else s.gdd_threshold

    current = "Sprouting"
    for stage in sorted(growth_stages, key=_threshold):
        if gdd_cumulative >= _threshold(stage):
            current = _name(stage)
        else:
            break
    return current


def _format_duration(hours: float) -> str:
    """Turn a duration in hours into a farmer-friendly label, e.g. 1.11 -> '1 hr 6 min'."""
    if hours <= 0:
        return "0 min"
    h = int(hours)
    m = int(round((hours - h) * 60))
    if m == 60:  # rounding edge case
        h, m = h + 1, 0
    if h and m:
        return f"{h} hr {m} min"
    if h:
        return f"{h} hr"
    return f"{m} min"


def compute_irrigation_requirement(
    et0_mm: float,
    crop_stage: str,
    field_area_m2: float,
    pump_discharge_l_s: float,
    rainfall_week_mm: float = 0.0,
    subtract_rainfall: bool = False,
) -> dict:
    """Deterministic AI irrigation-advisory rule (single-Kc, FAO-56).

    Implements the farmer-facing rule exactly:

        ETc (mm/day)      = ET0 * Kc
        Water Required (L)= ETc(mm/day) * Area(m2)          (1 mm over 1 m2 = 1 L)
        Pump Capacity     = Discharge(L/s) * 3600           (L/hr)
        Irrigation Time   = Water Required / Pump Capacity  (hr)

    If subtract_rainfall is True, effective rainfall (weekly rainfall * the
    effective fraction, averaged to a daily value) is deducted from ETc so the
    result is a NET irrigation requirement. Default False = gross ETc demand,
    matching the printed advisory rule.

    Returns a fully structured, JSON-serialisable dict. No Kcb / dual-coefficient
    term is used anywhere — single Kc only.
    """
    from .agronomy_constants import EFFECTIVE_RAINFALL_FRACTION, kc_for_stage

    kc = kc_for_stage(crop_stage)
    etc_mm_day = round(et0_mm * kc, 2)

    net_mm = etc_mm_day
    effective_rain_mm_day = 0.0
    if subtract_rainfall and rainfall_week_mm:
        effective_rain_mm_day = round((rainfall_week_mm * EFFECTIVE_RAINFALL_FRACTION) / 7.0, 2)
        net_mm = max(0.0, round(etc_mm_day - effective_rain_mm_day, 2))

    water_required_l = round(net_mm * field_area_m2, 1)
    pump_capacity_l_hr = round(pump_discharge_l_s * 3600, 1)
    hours = (water_required_l / pump_capacity_l_hr) if pump_capacity_l_hr else 0.0

    return {
        "crop_stage": crop_stage,
        "kc": kc,
        "et0_mm_day": round(et0_mm, 2),
        "etc_mm_day": etc_mm_day,
        "effective_rainfall_mm_day": effective_rain_mm_day,
        "net_requirement_mm_day": round(net_mm, 2),
        "field_area_m2": round(field_area_m2, 1),
        "water_required_l_day": water_required_l,
        "pump_discharge_l_s": pump_discharge_l_s,
        "pump_capacity_l_hr": pump_capacity_l_hr,
        "irrigation_time_hr": round(hours, 3),
        "irrigation_time_label": _format_duration(hours),
    }


def enrich_raw_weather(
    raw: RawDailyWeather,
    base_temp_c: float,
    latitude_deg: float = 18.1514,
    elevation_m: float = 560.0,
) -> dict:
    """Take a RawDailyWeather (from Open-Meteo) and attach the
    deterministically computed agronomy fields used throughout AgriAura.

    ET0 uses FAO-56 Penman-Monteith (per ET_and_Kc.docx) from Tmax, Tmin, RH,
    wind and solar. If solar radiation is missing it falls back to Hargreaves.
    """
    vpd = compute_vpd_kpa(raw.temp_max_c, raw.temp_min_c, raw.humidity_pct)
    if raw.solar_mj_m2 and raw.solar_mj_m2 > 0:
        et0 = compute_et0_penman_monteith(
            temp_max_c=raw.temp_max_c,
            temp_min_c=raw.temp_min_c,
            humidity_pct=raw.humidity_pct,
            wind_kmh=raw.wind_kmh or 0.0,
            solar_mj_m2=raw.solar_mj_m2,
            latitude_deg=latitude_deg,
            elevation_m=elevation_m,
            day_of_year=raw.date.timetuple().tm_yday,
        )
    else:
        et0 = compute_et0_hargreaves_mm(raw.temp_max_c, raw.temp_min_c, raw.solar_mj_m2)
    gdd_daily = compute_gdd(raw.temp_max_c, raw.temp_min_c, base_temp_c)
    return {
        "date": raw.date,
        "temp_max_c": raw.temp_max_c,
        "temp_min_c": raw.temp_min_c,
        "humidity_pct": raw.humidity_pct,
        "rainfall_mm": raw.rainfall_mm,
        "et0_mm": et0,
        "vpd_kpa": vpd,
        "solar_mj_m2": raw.solar_mj_m2,
        "wind_kmh": raw.wind_kmh,
        "gdd_daily": gdd_daily,
        "wind_direction_deg": raw.wind_direction_deg,
        "wind_gusts_kmh": raw.wind_gusts_kmh,
        "uv_index_max": raw.uv_index_max,
        "precipitation_probability_pct": raw.precipitation_probability_pct,
        "sunrise": raw.sunrise,
        "sunset": raw.sunset,
        "weather_code": raw.weather_code,
        "condition_text": text_for_weather_code(raw.weather_code),
    }


# ---------------------------------------------------------------------------
# Forecast-driven alert rules
# ---------------------------------------------------------------------------
# Each rule inspects the upcoming forecast (and recent history, for dry-spell
# detection) and yields zero or more alert dicts. sync_weather.py is responsible
# for turning these into Alert rows, deduplicated by rule_key so re-running sync
# doesn't spam duplicate alerts for the same underlying event.

def generate_weather_alerts(history: list, forecast: list, base_temp_c: float) -> list[dict]:
    """
    history / forecast: lists of ActualWeatherReading / ForecastWeatherReading model instances (or any object
    exposing the same attributes), history sorted ascending, forecast sorted
    ascending by date, both already saved to the DB by the time this runs.

    Returns a list of dicts: {severity, icon, title, description, rule_key}
    """
    alerts: list[dict] = []

    # --- Heavy rain tomorrow ---
    if forecast:
        tomorrow = forecast[0]
        if tomorrow.rainfall_mm >= 25:
            alerts.append(
                {
                    "severity": "warning",
                    "icon": "🌧️",
                    "title": f"Heavy Rain Expected Tomorrow ({tomorrow.rainfall_mm:.0f}mm)",
                    "description": (
                        f"{tomorrow.rainfall_mm:.0f}mm forecast for {tomorrow.date}. "
                        "Skip irrigation and check drainage channels are clear before it arrives."
                    ),
                    "rule_key": f"heavy_rain_{tomorrow.date}",
                }
            )

    # --- Dry spell: 4+ consecutive days with <2mm rainfall across history+forecast ---
    combined = list(history[-4:]) + list(forecast[:3])
    if len(combined) >= 4:
        dry_streak = 0
        max_streak = 0
        max_streak_end_date = None
        for r in combined:
            if r.rainfall_mm < 2:
                dry_streak += 1
                if dry_streak > max_streak:
                    max_streak = dry_streak
                    max_streak_end_date = r.date
            else:
                dry_streak = 0
        if max_streak >= 4:
            alerts.append(
                {
                    "severity": "warning",
                    "icon": "🏜️",
                    "title": f"{max_streak}-Day Dry Spell Detected",
                    "description": (
                        f"Less than 2mm rainfall for {max_streak} consecutive days through "
                        f"{max_streak_end_date}. Soil moisture is likely depleting — check the "
                        "irrigation page for today's recommendation."
                    ),
                    "rule_key": f"dry_spell_{max_streak_end_date}",
                }
            )

    # --- Heatwave: 3+ consecutive forecast days above 38°C ---
    if len(forecast) >= 3:
        hot_streak = 0
        for r in forecast:
            if r.temp_max_c >= 38:
                hot_streak += 1
                if hot_streak >= 3:
                    alerts.append(
                        {
                            "severity": "critical",
                            "icon": "🔥",
                            "title": f"Heatwave Warning ({r.temp_max_c:.0f}°C+)",
                            "description": (
                                f"3+ consecutive days forecast above 38°C, peaking at "
                                f"{r.temp_max_c:.0f}°C on {r.date}. Increased irrigation may be "
                                "needed; avoid fieldwork during peak afternoon heat."
                            ),
                            "rule_key": f"heatwave_{r.date}",
                        }
                    )
                    break
            else:
                hot_streak = 0

    # --- Cold/chill risk near sprouting stage ---
    if forecast:
        coldest = min(forecast, key=lambda r: r.temp_min_c)
        if coldest.temp_min_c < (base_temp_c - 5):
            alerts.append(
                {
                    "severity": "warning",
                    "icon": "❄️",
                    "title": f"Low Temperature Alert ({coldest.temp_min_c:.0f}°C)",
                    "description": (
                        f"Minimum temperature of {coldest.temp_min_c:.0f}°C forecast for "
                        f"{coldest.date}, below the {base_temp_c:.0f}°C base temperature for "
                        "GDD accumulation. Growth may slow during this period."
                    ),
                    "rule_key": f"cold_snap_{coldest.date}",
                }
            )

    # --- High wind / spray-drift warning ---
    for r in forecast[:3]:
        gusts = getattr(r, "wind_gusts_kmh", None)
        if gusts and gusts >= 35:
            alerts.append(
                {
                    "severity": "info",
                    "icon": "💨",
                    "title": f"Strong Wind Gusts Forecast ({gusts:.0f} km/h)",
                    "description": (
                        f"Gusts up to {gusts:.0f} km/h expected on {r.date}. Avoid spraying "
                        "fungicide or pesticide on this day — drift risk is high."
                    ),
                    "rule_key": f"high_wind_{r.date}",
                }
            )
            break

    # --- High UV — field worker safety ---
    for r in forecast[:2]:
        uv = getattr(r, "uv_index_max", None)
        if uv and uv >= 9:
            alerts.append(
                {
                    "severity": "info",
                    "icon": "☀️",
                    "title": f"Very High UV Index ({uv:.0f})",
                    "description": (
                        f"UV index reaching {uv:.0f} on {r.date}. Field workers should avoid "
                        "prolonged sun exposure between 11am-3pm; wear hats and cover up."
                    ),
                    "rule_key": f"high_uv_{r.date}",
                }
            )
            break

    return alerts
