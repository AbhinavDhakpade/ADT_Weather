"""Unauthenticated liveness/readiness probe for load balancers and Docker healthchecks."""

import datetime

from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.utils import timezone


def health(request):
    """
    GET /api/health/
      200 {"status": "ok", ...}        database reachable
      503 {"status": "unavailable"}    database unreachable
    `sync` says whether the weather scheduler has completed a run recently; a stale
    sync does NOT fail the probe (restarting the web container would not fix it).
    """
    try:
        connection.ensure_connection()
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
    except Exception:  # noqa: BLE001
        return JsonResponse({"status": "unavailable", "database": "down"}, status=503)

    sync = "unknown"
    try:
        from advisory.models import SchedulerLog

        last = SchedulerLog.objects.order_by("-started_at").first()
        if last is not None:
            limit = datetime.timedelta(minutes=2 * settings.WEATHER_SYNC_INTERVAL_MINUTES + 5)
            sync = "fresh" if timezone.now() - last.started_at <= limit else "stale"
    except Exception:  # noqa: BLE001  (e.g. migrations not applied yet)
        sync = "unknown"
    return JsonResponse({"status": "ok", "database": "up", "sync": sync})
