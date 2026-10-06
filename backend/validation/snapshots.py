"""Records forecast snapshots. Called from advisory.sync_service after every forecast sync."""

import logging

from .models import ForecastSnapshot

logger = logging.getLogger("validation.snapshots")

SNAPSHOT_FIELDS = [
    "temp_max_c", "temp_min_c", "humidity_pct", "rainfall_mm", "solar_mj_m2",
    "wind_kmh", "et0_mm", "precipitation_probability_pct",
]


def record_forecast_snapshots(farm, issued_at):
    """
    Store the farm's current forecast rows as snapshots, one per target date.

    The lead time is counted from the first date in the batch: Open-Meteo is
    asked for timezone=auto, so its first forecast day is the farm's local
    "today". The first sync of each lead-day wins (get_or_create): later syncs the
    same day do not overwrite it, so lead N always means "issued about N days earlier".
    Returns the number of snapshots created. Never raises - this must not break a sync.
    """
    try:
        rows = list(farm.forecast_weather_readings.filter(data_source="open_meteo").order_by("date"))
        if not rows:
            return 0
        first_date = rows[0].date
        created_count = 0
        for row in rows:
            lead = (row.date - first_date).days
            _, created = ForecastSnapshot.objects.get_or_create(
                farm=farm, target_date=row.date, lead_days=lead,
                defaults={
                    "issued_at": issued_at,
                    "source": row.data_source,
                    **{f: getattr(row, f) for f in SNAPSHOT_FIELDS},
                },
            )
            created_count += int(created)
        return created_count
    except Exception:  # noqa: BLE001 - snapshots are best-effort
        logger.exception("Could not record forecast snapshots for %s", farm)
        return 0
