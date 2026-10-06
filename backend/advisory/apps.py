import os
import sys

from django.apps import AppConfig


class AdvisoryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "advisory"

    def ready(self):
        """
        Starts the automatic hourly weather-sync scheduler exactly once, only
        for processes that actually serve the app — never for one-off
        management commands like migrate/makemigrations/test/shell/seed_data,
        and never twice under `runserver`'s auto-reloader (which spawns a
        watcher parent process in addition to the real server process).
        """
        argv0 = sys.argv[0] if sys.argv else ""
        is_manage_py = "manage.py" in argv0

        if is_manage_py:
            if len(sys.argv) < 2 or sys.argv[1] != "runserver":
                return  # migrate / makemigrations / test / shell / seed_data / etc.
            # --noreload never sets RUN_MAIN; the reloader's child process
            # sets it to "true". Treat "unset" (no reloader in play) as OK too.
            if os.environ.get("RUN_MAIN") not in (None, "true"):
                return
        # Otherwise this is a WSGI/ASGI server process (gunicorn/uvicorn/daphne).
        # Note: for a multi-worker production deployment, only one worker
        # should own the schedule — set SCHEDULER_AUTOSTART=False on the
        # others, or trigger sync externally via POST /api/scheduler/run-now/.

        from . import scheduler

        scheduler.start()
