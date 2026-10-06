#!/bin/sh
# Container entrypoint.
#   gunicorn ...            -> web role: wait for DB, migrate, collect static, load reference tables, serve
#   anything else           -> wait for DB, then run the given command (scheduler, management commands)
set -eu

python - <<'PY'
import sys, time, django
django.setup()
from django.db import connection
for attempt in range(60):
    try:
        connection.ensure_connection()
        sys.exit(0)
    except Exception as exc:  # noqa: BLE001
        print(f"waiting for database ({attempt + 1}/60): {exc}", flush=True)
        time.sleep(2)
sys.exit("database not reachable after 120 s")
PY

if [ "${1:-}" = "gunicorn" ]; then
    python manage.py migrate --noinput
    python manage.py collectstatic --noinput --verbosity 0
    # Reference tables only (diseases, treatments, irrigation rules): idempotent, never touches farms or weather.
    python manage.py seed_data --reference-only
fi

exec "$@"
