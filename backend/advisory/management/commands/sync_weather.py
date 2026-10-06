"""
Management command: sync_weather

Thin CLI wrapper around advisory.sync_service.run_weather_sync() — the same
function the automatic hourly APScheduler job and the dashboard's manual
"Refresh" button call, so a CLI run, a scheduled run, and a manual run all
produce identical, comparable SchedulerLog rows.

Useful for:
  - A one-off manual sync during development.
  - An external cron/systemd-timer fallback if you'd rather not rely on the
    in-process APScheduler (e.g. multi-worker gunicorn deployments where you
    set SCHEDULER_AUTOSTART=False on every worker and drive syncs from cron
    instead — see advisory/scheduler.py).

Usage:
    python manage.py sync_weather                  # all farms
    python manage.py sync_weather --farm 1          # a specific farm
    python manage.py sync_weather --history-days 7 --forecast-days 7
    python manage.py sync_weather --no-alerts       # skip alert generation
"""

from django.core.management.base import BaseCommand

from advisory.models import FarmProfile
from advisory.sync_service import run_weather_sync


class Command(BaseCommand):
    help = "Sync ActualWeatherReading (Open-Meteo history) and ForecastWeatherReading (Open-Meteo forecast) rows."

    def add_arguments(self, parser):
        parser.add_argument("--farm", type=int, default=None, help="Only sync this farm id")
        parser.add_argument("--history-days", type=int, default=7)
        parser.add_argument("--forecast-days", type=int, default=7)
        parser.add_argument("--no-alerts", action="store_true", help="Skip forecast-driven alert generation")
        parser.add_argument(
            "--trigger", type=str, default="manual",
            choices=["manual", "scheduled", "startup"],
            help="How this run should be labeled in SchedulerLog (default: manual)",
        )

    def handle(self, *args, **options):
        farms = FarmProfile.objects.all()
        if options["farm"]:
            farms = farms.filter(pk=options["farm"])

        if not farms.exists():
            self.stdout.write(self.style.WARNING("No farms found. Run seed_data first."))
            return

        log = run_weather_sync(
            farm_qs=farms,
            history_days=options["history_days"],
            forecast_days=options["forecast_days"],
            generate_alerts=not options["no_alerts"],
            trigger=options["trigger"],
        )

        style = self.style.SUCCESS if log.status == "success" else (
            self.style.WARNING if log.status == "partial" else self.style.ERROR
        )
        self.stdout.write(style(
            f"Sync {log.status}: {log.farms_processed} farm(s), {log.records_fetched} record(s) "
            f"({log.records_updated} updated, {log.duplicates_removed} duplicates skipped), "
            f"{log.retry_attempts} retry attempt(s), {log.duration_seconds}s. "
            f"Open-Meteo history: {log.history_status}, Open-Meteo forecast: {log.open_meteo_status}."
        ))
        if log.error_message:
            self.stdout.write(self.style.WARNING(f"Details: {log.error_message}"))
