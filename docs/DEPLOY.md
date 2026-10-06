# Deploying AgriAura (PostgreSQL + Docker Compose)

    cp .env.example .env        # fill DJANGO_SECRET_KEY, POSTGRES_PASSWORD, host names
    docker compose up -d --build
    docker compose exec backend python manage.py createsuperuser

Services: `db` (PostgreSQL 16), `backend` (Django + gunicorn), `scheduler` (the only process that
syncs weather), `web` (nginx + React, proxies /api, /admin, /static), `backup` (daily pg_dump, 14 days kept).

* **Data-centre storage:** set `PGDATA_PATH` and `BACKUP_PATH` in `.env` to paths on the mounted storage service.
* **TLS:** terminate it in front of this stack and send `X-Forwarded-Proto: https`; set `DJANGO_HTTPS=True`.
* **Outbound network:** the `scheduler` and `backend` containers must be able to reach `api.open-meteo.com` and
  `archive-api.open-meteo.com` over HTTPS (port 443). Open-Meteo is the only weather provider; no API key is needed.
  Check with `docker compose logs scheduler` and the dashboard's Scheduler Monitoring panel (`history_status`,
  `open_meteo_status`). Optional `OPEN_METEO_*` overrides are in `.env.example`.
* **Upgrading an existing deployment:** `migrate` runs automatically on start; migration `0011` renames
  `SchedulerLog.nasa_power_status` to `history_status` and keeps every existing row. Stored weather readings are untouched.
* **Station files / reports:** `./exchange` is mounted at `/exchange` in the backend container.
    docker compose exec backend python manage.py import_station_data /exchange/station.csv --station "AWS" --farm 1
    docker compose exec backend python manage.py validate_weather --out-dir /exchange/reports
* **Moving existing SQLite data:** with the old settings run `python manage.py dumpdata --natural-foreign
  --natural-primary -e contenttypes -e auth.permission > data.json`, then on the new stack
  `docker compose exec backend python manage.py loaddata /exchange/data.json`.
  Rebuild ids with `sqlsequencereset advisory validation | psql` if you insert rows afterwards.
* **Restore:** `pg_restore -h db -U agriaura -d agriaura --clean <dump>`.
* Run only ONE scheduler. The web workers are started with `SCHEDULER_AUTOSTART=False`.
* Never commit `.env`; it is git-ignored.
