#!/bin/sh
# A verified pre-migration backup. Required failures block application startup.
set -eu
mode=${BACKUP_MODE:-required}
keep=${BACKUP_KEEP:-10}
case "$mode" in required|best-effort|off) ;; *) echo 'Invalid BACKUP_MODE' >&2; exit 1;; esac
case "$keep" in ''|*[!0-9]*|0) echo 'BACKUP_KEEP must be a positive integer' >&2; exit 1;; esac
[ "$keep" -gt 0 ] || { echo 'BACKUP_KEEP must be a positive integer' >&2; exit 1; }
[ "$mode" = off ] && exit 0
destination="/backups/vadat-$(date -u +%Y%m%dT%H%M%S)-$$.dump"
partial="$destination.partial"
trap 'rm -f "$partial"' EXIT
if pg_dump -Fc -f "$partial" && pg_restore --list "$partial" >/dev/null && mv "$partial" "$destination"; then
  count=0
  for file in $(ls -1t /backups/vadat-*.dump); do
    count=$((count + 1))
    if [ "$count" -gt "$keep" ]; then rm -f "$file"; fi
  done
  echo 'Verified pre-migration backup saved.'
elif [ "$mode" = best-effort ]; then
  echo 'WARNING: backup failed; best-effort mode allows migration.' >&2
else
  echo 'Backup failed; migrations must not run.' >&2
  exit 1
fi
