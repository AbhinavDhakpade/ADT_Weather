"""
Background scheduler: automatically runs the weather sync every N minutes
(default 60 — one hour) with zero manual intervention, per-farm retry logic,
and a SchedulerLog row per run. See advisory/apps.py for how/when this gets
started, and advisory/sync_service.py for the actual sync + retry logic.

This uses APScheduler's BackgroundScheduler, which runs an in-process daemon
thread — no separate worker process, broker, or Redis instance required,
which keeps a SQLite-based deployment simple. If you later move to
PostgreSQL/Celery Beat for a multi-process production deployment, this module
is the only place that needs replacing; sync_service.run_weather_sync() stays
the same either way.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger("advisory.scheduler")

JOB_ID = "weather_sync_hourly"

# Module-level singleton — a Django process should only ever run one of these.
_scheduler = None


def _run_sync_job():
    """The actual APScheduler job body. Imported lazily so Django apps are
    fully loaded before models/settings get touched."""
    from .sync_service import run_weather_sync

    logger.info("Scheduled weather sync starting…")
    log = run_weather_sync(trigger="scheduled")
    logger.info("Scheduled weather sync finished: %s", log.status)


def start():
    """
    Idempotently starts the background scheduler. Safe to call more than
    once — subsequent calls are no-ops if a scheduler is already running.
    Returns the running scheduler, or None if autostart is disabled.
    """
    global _scheduler

    if _scheduler is not None:
        return _scheduler

    if not getattr(settings, "SCHEDULER_AUTOSTART", True):
        logger.info("Weather scheduler autostart disabled (SCHEDULER_AUTOSTART=False).")
        return None

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.interval import IntervalTrigger
    except ImportError:
        logger.warning(
            "APScheduler is not installed — automatic hourly weather sync is disabled. "
            "Install it with `pip install apscheduler` (see requirements.txt), or run "
            "`python manage.py sync_weather` on a cron/systemd timer instead."
        )
        return None

    interval_minutes = int(getattr(settings, "WEATHER_SYNC_INTERVAL_MINUTES", 60))

    scheduler = BackgroundScheduler(timezone=str(timezone.get_current_timezone()))
    scheduler.add_job(
        _run_sync_job,
        trigger=IntervalTrigger(minutes=interval_minutes),
        id=JOB_ID,
        name="AgriAura hourly weather sync",
        replace_existing=True,
        # Run an initial catch-up sync shortly after startup rather than
        # waiting a full interval for the first data — "no manual
        # intervention" means fresh data from the moment the server starts.
        next_run_time=timezone.now() + timedelta(seconds=20),
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
    )
    scheduler.start()
    _scheduler = scheduler
    logger.info(
        "APScheduler started: weather sync every %d minute(s), first run in ~20s.",
        interval_minutes,
    )
    return scheduler


def get_scheduler():
    """Returns the running BackgroundScheduler instance, or None if not started."""
    return _scheduler


def shutdown():
    """Stops the scheduler cleanly (used by tests / graceful shutdown hooks)."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
