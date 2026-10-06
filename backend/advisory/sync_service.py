"""
Core weather-sync logic, shared by three callers:
  - advisory/scheduler.py     (automatic hourly APScheduler job — no manual intervention)
  - management/commands/sync_weather.py  (CLI, e.g. cron/systemd-timer fallback)
  - views.refresh_weather_now / views.scheduler_run_now  (user-triggered "Refresh")

Every call to run_weather_sync() writes exactly one SchedulerLog row summarizing
the whole run (all farms), so the dashboard's Scheduler Monitoring panel has a
single source of truth regardless of what triggered the sync.

Retry behaviour: each Open-Meteo call (history, forecast) is retried up
to WEATHER_SYNC_MAX_RETRIES times with exponential backoff (2s, 4s, 8s, ...)
before that source is marked "failed" for the run. A source failing for one
farm doesn't stop the others — the run is marked "partial" rather than
"failure" as long as at least one farm synced something.
"""

import datetime
import logging
import time

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import (
    ActualWeatherReading,
    Alert,
    FarmProfile,
    ForecastWeatherReading,
    IrrigationRequirementLog,
    SchedulerLog,
)
from .weather_service import (
    WeatherServiceError,
    compute_irrigation_requirement,
    enrich_raw_weather,
    fetch_open_meteo_forecast,
    fetch_open_meteo_history,
    SOURCE_ARCHIVE,
    generate_weather_alerts,
    icon_for_weather_code,
)

logger = logging.getLogger("advisory.scheduler")

# Fields that exist on both weather models directly from enrich_raw_weather's output,
# excluding ones that need special handling (date, sunrise/sunset as strings).
DIRECT_FIELDS = [
    "temp_max_c", "temp_min_c", "humidity_pct", "rainfall_mm", "et0_mm", "vpd_kpa",
    "solar_mj_m2", "wind_kmh", "gdd_daily", "wind_direction_deg", "wind_gusts_kmh",
    "uv_index_max", "precipitation_probability_pct", "weather_code", "condition_text",
]


def _parse_time(value):
    """'05:48' -> datetime.time(5, 48); passes through None."""
    if not value:
        return None
    try:
        hh, mm = value.split(":")[:2]
        return datetime.time(int(hh), int(mm))
    except (ValueError, AttributeError):
        return None


PREDICTION_MODEL_LABEL = "Open-Meteo (ICON/GFS blend)"


def _forecast_confidence(target_date, as_of):
    """
    0-1 confidence score for a forecast row, decaying with lead time — a
    tomorrow forecast is materially more reliable than a 7-day-out one.
    Values roughly track published Open-Meteo/ECMWF skill-score curves:
    ~0.95 for today, ~0.55 by day 7.
    """
    lead_days = max((target_date - as_of).days, 0)
    return round(max(0.55, 0.95 - 0.055 * lead_days), 2)


def _fetch_with_retry(fetch_fn, *args, max_retries=3, **kwargs):
    """
    Calls fetch_fn(*args, **kwargs). On WeatherServiceError, retries with
    exponential backoff (2s, 4s, 8s, ...) up to max_retries attempts total.
    Returns (result_list_or_empty, attempts_used, last_error_or_None).
    """
    last_error = None
    for attempt in range(1, max(1, max_retries) + 1):
        try:
            return fetch_fn(*args, **kwargs), attempt, None
        except WeatherServiceError as exc:
            last_error = exc
            logger.warning(
                "%s attempt %d/%d failed: %s", getattr(fetch_fn, "__name__", repr(fetch_fn)), attempt, max_retries, exc
            )
            if attempt < max_retries:
                time.sleep(2 ** (attempt - 1))
    return [], max_retries, last_error


def sync_farm(farm, history_days=7, forecast_days=7, generate_alerts=True, max_retries=3):
    """
    Syncs one farm's weather (Open-Meteo history + Open-Meteo forecast),
    de-duplicating same-date records within a batch and upserting into
    ActualWeatherReading/ForecastWeatherReading. Never raises on API failure — failures are captured in the
    returned stats dict so one farm's bad API call can't abort the whole run.
    """
    stats = {
        "records_fetched": 0,
        "records_updated": 0,
        "duplicates_removed": 0,
        "retry_attempts": 0,
        "history_status": "ok",
        "open_meteo_status": "ok",  # forecast request
        "errors": [],
    }
    now = timezone.now()

    history_raw, attempts, err = _fetch_with_retry(
        fetch_open_meteo_history, farm.latitude, farm.longitude, days=history_days, max_retries=max_retries
    )
    stats["retry_attempts"] += attempts - 1
    if err:
        stats["history_status"] = "failed"
        stats["errors"].append(f"{farm}: Open-Meteo history — {err}")

    forecast_raw, attempts2, err2 = _fetch_with_retry(
        fetch_open_meteo_forecast, farm.latitude, farm.longitude, days=forecast_days, max_retries=max_retries
    )
    stats["retry_attempts"] += attempts2 - 1
    if err2:
        stats["open_meteo_status"] = "failed"
        stats["errors"].append(f"{farm}: Open-Meteo forecast — {err2}")

    if not history_raw and not forecast_raw:
        stats["errors"].append(f"{farm}: both sources failed — nothing synced.")
        return stats

    today = timezone.localdate()

    with transaction.atomic():
        # History (Open-Meteo) -> ActualWeatherReading — ascending so cumulative
        # GDD accrues correctly.
        history_sorted = sorted(history_raw, key=lambda r: r.date)

        # Running GDD cumulative total. Every sync re-fetches days that are
        # already stored, so the total must start from the reading just BEFORE
        # the first fetched day. Starting from the newest stored reading (as
        # this used to) added the same days again on every run, inflating the
        # total by a full history window each time.
        if history_sorted:
            baseline = (
                ActualWeatherReading.objects.filter(farm=farm, date__lt=history_sorted[0].date)
                .order_by("-date")
                .first()
            )
        else:  # history request failed: forecast continues from the newest stored day
            baseline = ActualWeatherReading.objects.filter(farm=farm).order_by("-date").first()
        cumulative = baseline.gdd_cumulative if baseline else 0.0

        seen_dates = set()
        for raw in history_sorted:
            if raw.date in seen_dates:
                stats["duplicates_removed"] += 1
                continue
            seen_dates.add(raw.date)
            enriched = enrich_raw_weather(raw, farm.base_temp_c, farm.latitude, farm.elevation_m)
            if raw.date >= farm.planting_date:  # GDD counts from planting, not before it
                cumulative += enriched["gdd_daily"]
            defaults = {k: enriched[k] for k in DIRECT_FIELDS}
            defaults.update(
                gdd_cumulative=round(cumulative, 1),
                weather_icon="⛅",
                sunrise=_parse_time(enriched.get("sunrise")),
                sunset=_parse_time(enriched.get("sunset")),
                data_source=raw.source or SOURCE_ARCHIVE,
                fetched_at=now,
            )
            _, created = ActualWeatherReading.objects.update_or_create(
                farm=farm, date=enriched["date"], defaults=defaults
            )
            stats["records_fetched"] += 1
            if not created:
                stats["records_updated"] += 1

        # Forecast (Open-Meteo) -> ForecastWeatherReading — continues cumulative
        # GDD forward from history. Drop stale forecast rows whose date isn't in
        # this batch so past forecast dates don't linger once they roll into history.
        forecast_sorted = sorted(forecast_raw, key=lambda r: r.date)
        forecast_dates = {r.date for r in forecast_sorted}
        if forecast_dates:
            ForecastWeatherReading.objects.filter(farm=farm).exclude(date__in=forecast_dates).delete()
        f_seen = set()
        for raw in forecast_sorted:
            if raw.date in f_seen:
                stats["duplicates_removed"] += 1
                continue
            f_seen.add(raw.date)
            enriched = enrich_raw_weather(raw, farm.base_temp_c, farm.latitude, farm.elevation_m)
            if raw.date >= farm.planting_date:
                cumulative += enriched["gdd_daily"]
            defaults = {k: enriched[k] for k in DIRECT_FIELDS}
            defaults.update(
                gdd_cumulative=round(cumulative, 1),
                weather_icon=icon_for_weather_code(raw.weather_code),
                sunrise=_parse_time(enriched.get("sunrise")),
                sunset=_parse_time(enriched.get("sunset")),
                data_source="open_meteo",
                fetched_at=now,
                confidence_score=_forecast_confidence(enriched["date"], today),
                prediction_model=PREDICTION_MODEL_LABEL,
            )
            _, created = ForecastWeatherReading.objects.update_or_create(
                farm=farm, date=enriched["date"], defaults=defaults
            )
            stats["records_fetched"] += 1
            if not created:
                stats["records_updated"] += 1

    # Keep the forecast as issued (ForecastWeatherReading is overwritten on every
    # sync) so it can later be compared with a weather station. Best-effort.
    if forecast_raw:
        from validation.snapshots import record_forecast_snapshots

        record_forecast_snapshots(farm, now)

    # Stage 2 of the weather -> irrigation pipeline: now that today's ET0 is
    # stored, compute and persist the deterministic irrigation requirement.
    try:
        irrigation_log = compute_and_store_irrigation(farm)
        if irrigation_log is not None:
            stats["irrigation_time_label"] = irrigation_log.irrigation_time_label
    except Exception as exc:  # never let advisory calc abort a weather sync
        stats["errors"].append(f"{farm}: irrigation calc — {exc}")

    if generate_alerts:
        _run_alert_rules(farm)

    return stats


def compute_and_store_irrigation(farm):
    """Weather -> irrigation pipeline (Stage 2).

    Consumes the deterministic ET0 produced by the weather stage (already stored
    on the latest ActualWeatherReading) and the farm's pump inputs, runs the
    single-Kc irrigation rule, and upserts one IrrigationRequirementLog row for
    today. Returns the log row, or None if there's no weather yet.
    """
    today_reading = (
        ActualWeatherReading.objects.filter(farm=farm).order_by("-date").first()
    )
    if today_reading is None:
        return None

    rainfall_week = sum(
        r.rainfall_mm
        for r in ActualWeatherReading.objects.filter(farm=farm).order_by("-date")[:7]
    )
    crop_stage = farm.current_crop_stage(today_reading.gdd_cumulative)

    result = compute_irrigation_requirement(
        et0_mm=today_reading.et0_mm,
        crop_stage=crop_stage,
        field_area_m2=farm.area_m2,
        pump_discharge_l_s=farm.pump_discharge_l_s,
        rainfall_week_mm=rainfall_week,
        subtract_rainfall=False,  # gross ETc demand (matches the printed rule)
    )

    log, _ = IrrigationRequirementLog.objects.update_or_create(
        farm=farm,
        date=today_reading.date,
        defaults={
            "crop_stage": result["crop_stage"],
            "kc": result["kc"],
            "et0_mm_day": result["et0_mm_day"],
            "etc_mm_day": result["etc_mm_day"],
            "effective_rainfall_mm_day": result["effective_rainfall_mm_day"],
            "net_requirement_mm_day": result["net_requirement_mm_day"],
            "field_area_m2": result["field_area_m2"],
            "water_required_l_day": result["water_required_l_day"],
            "pump_hp": farm.pump_hp,
            "pump_discharge_l_s": result["pump_discharge_l_s"],
            "pump_capacity_l_hr": result["pump_capacity_l_hr"],
            "irrigation_time_hr": result["irrigation_time_hr"],
            "irrigation_time_label": result["irrigation_time_label"],
        },
    )
    return log


def _run_alert_rules(farm):
    history = list(ActualWeatherReading.objects.filter(farm=farm).order_by("-date")[:7])
    history.reverse()
    forecast = list(ForecastWeatherReading.objects.filter(farm=farm).order_by("date"))
    rule_alerts = generate_weather_alerts(history, forecast, farm.base_temp_c)

    for a in rule_alerts:
        Alert.objects.update_or_create(
            farm=farm,
            rule_key=a["rule_key"],
            defaults={
                "severity": a["severity"],
                "icon": a["icon"],
                "title": a["title"],
                "description": a["description"],
                "source": "weather_rule",
                "is_active": True,
            },
        )

    # Deactivate stale weather-rule alerts whose rule_key wasn't regenerated
    # this run (e.g. a "heavy rain tomorrow" alert ages out once "tomorrow" passes).
    active_keys = {a["rule_key"] for a in rule_alerts}
    Alert.objects.filter(farm=farm, source="weather_rule", is_active=True).exclude(
        rule_key__in=active_keys
    ).update(is_active=False)


def run_weather_sync(farm_qs=None, history_days=7, forecast_days=7, generate_alerts=True,
                      trigger="scheduled", max_retries=None):
    """
    Top-level entry point: syncs every farm in farm_qs (default: all farms),
    aggregates results, and writes exactly one SchedulerLog row for the run.
    Used by the APScheduler job, the sync_weather management command, and the
    manual-refresh / run-now API endpoints — so every trigger path produces
    identical, comparable log rows.
    """
    if max_retries is None:
        max_retries = getattr(settings, "WEATHER_SYNC_MAX_RETRIES", 3)

    started = timezone.now()
    farms = farm_qs if farm_qs is not None else FarmProfile.objects.all()
    farm_list = list(farms)

    agg = {
        "farms_processed": 0,
        "records_fetched": 0,
        "records_updated": 0,
        "duplicates_removed": 0,
        "retry_attempts": 0,
    }
    history_ok, open_meteo_ok = True, True
    errors = []

    if not farm_list:
        errors.append("No farm profiles exist yet — run seed_data first.")

    for farm in farm_list:
        try:
            stats = sync_farm(farm, history_days, forecast_days, generate_alerts, max_retries)
        except Exception as exc:  # noqa: BLE001 — a bad farm must never kill the whole run
            logger.exception("Unhandled error syncing farm %s", farm.pk)
            errors.append(f"{farm}: unexpected error — {exc}")
            continue

        if stats["records_fetched"] > 0:
            agg["farms_processed"] += 1
        agg["records_fetched"] += stats["records_fetched"]
        agg["records_updated"] += stats["records_updated"]
        agg["duplicates_removed"] += stats["duplicates_removed"]
        agg["retry_attempts"] += stats["retry_attempts"]
        if stats["history_status"] == "failed":
            history_ok = False
        if stats["open_meteo_status"] == "failed":
            open_meteo_ok = False
        errors.extend(stats["errors"])

    finished = timezone.now()
    if agg["farms_processed"] == 0:
        status = "failure"
    elif errors:
        status = "partial"
    else:
        status = "success"

    log = SchedulerLog.objects.create(
        task_name="sync_weather",
        trigger=trigger,
        started_at=started,
        finished_at=finished,
        duration_seconds=round((finished - started).total_seconds(), 2),
        status=status,
        farms_processed=agg["farms_processed"],
        records_fetched=agg["records_fetched"],
        records_updated=agg["records_updated"],
        duplicates_removed=agg["duplicates_removed"],
        retry_attempts=agg["retry_attempts"],
        history_status="ok" if history_ok else "failed",
        open_meteo_status="ok" if open_meteo_ok else "failed",
        error_message="; ".join(errors)[:4000],
    )

    logger.info(
        "Weather sync (%s) finished: %s — %d farm(s), %d record(s), %.1fs",
        trigger, status, agg["farms_processed"], agg["records_fetched"], log.duration_seconds,
    )
    return log
