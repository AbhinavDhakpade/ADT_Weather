#!/bin/sh
# Daily PostgreSQL backup loop (runs in the `backup` service). Custom format (-Fc) is already compressed;
# restore with pg_restore. Keeps BACKUP_KEEP_DAYS days (default 14).
set -u
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
INTERVAL_HOURS="${BACKUP_INTERVAL_HOURS:-24}"
mkdir -p /backups
while true; do
    FILE="/backups/agriaura_$(date +%Y%m%d_%H%M%S).dump"
    if pg_dump -h db -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f "$FILE.partial"; then
        mv "$FILE.partial" "$FILE"
        echo "backup ok: $FILE ($(du -h "$FILE" | cut -f1))"
    else
        rm -f "$FILE.partial"
        echo "BACKUP FAILED at $(date)" >&2
    fi
    find /backups -name 'agriaura_*.dump' -mtime +"$KEEP_DAYS" -delete
    sleep $((INTERVAL_HOURS * 3600))
done
