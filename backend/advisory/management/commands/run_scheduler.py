"""
Run the weather scheduler as its own long-lived process.

    python manage.py run_scheduler            # sync every WEATHER_SYNC_INTERVAL_MINUTES, forever
    python manage.py run_scheduler --once     # one sync, then exit (for cron / systemd timers)

Why this exists: the in-process scheduler (advisory/scheduler.py) lives inside the web
server, so with several gunicorn workers it would run the sync several times. In
production the web containers set SCHEDULER_AUTOSTART=False and exactly one container
runs this command instead. On PostgreSQL an advisory lock additionally guarantees that
two accidental copies can never sync at the same moment.
"""

import logging
import signal
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone

from advisory.sync_service import run_weather_sync

logger = logging.getLogger("advisory.scheduler")

LOCK_ID = 7_407_001  # arbitrary, app-specific advisory lock key


def _try_lock() -> bool:
    if connection.vendor != "postgresql":
        return True
    with connection.cursor() as cur:
        cur.execute("SELECT pg_try_advisory_lock(%s)", [LOCK_ID])
        return bool(cur.fetchone()[0])


def _unlock():
    if connection.vendor == "postgresql":
        with connection.cursor() as cur:
            cur.execute("SELECT pg_advisory_unlock(%s)", [LOCK_ID])


def run_job(trigger="scheduled"):
    """One guarded sync. Returns the SchedulerLog, or None if another scheduler holds the lock."""
    if not _try_lock():
        logger.warning("Another scheduler is already syncing; skipping this run.")
        return None
    try:
        log = run_weather_sync(trigger=trigger)
        logger.info("Weather sync finished: %s (%s farm(s), %s records)", log.status, log.farms_processed, log.records_fetched)
        return log
    except Exception:  # noqa: BLE001 - one bad run must never kill the scheduler
        logger.exception("Weather sync crashed")
        return None
    finally:
        try:
            _unlock()
        except Exception:  # noqa: BLE001
            logger.exception("Could not release the advisory lock")


class Command(BaseCommand):
    help = "Run the periodic weather sync in a dedicated process (production scheduler)."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Run a single sync and exit")
        parser.add_argument("--interval", type=int, default=None, help="Minutes between syncs (default: WEATHER_SYNC_INTERVAL_MINUTES)")
        parser.add_argument("--startup-delay", type=int, default=20, help="Seconds before the first run (default 20)")

    def handle(self, *args, **options):
        if options["once"]:
            run_job(trigger="manual")
            return

        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.interval import IntervalTrigger

        interval = options["interval"] or settings.WEATHER_SYNC_INTERVAL_MINUTES
        scheduler = BlockingScheduler(timezone=str(timezone.get_current_timezone()))
        scheduler.add_job(
            run_job, IntervalTrigger(minutes=interval), id="weather_sync_dedicated",
            name="AgriAura weather sync", max_instances=1, coalesce=True, misfire_grace_time=300,
            next_run_time=timezone.now() + timedelta(seconds=options["startup_delay"]),
        )

        def _stop(signum, _frame):
            logger.info("Received signal %s, stopping scheduler.", signum)
            scheduler.shutdown(wait=False)

        signal.signal(signal.SIGTERM, _stop)
        signal.signal(signal.SIGINT, _stop)
        self.stdout.write(self.style.SUCCESS(f"Weather scheduler running: sync every {interval} minute(s)."))
        scheduler.start()
