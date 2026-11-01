#!/bin/sh
set -eu
umask 077
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
WORK="$ROOT/.runtime/backups/$STAMP"
mkdir -p "$WORK"

if [ "${ARMY_BACKUP_IN_DOCKER:-0}" = "1" ]; then
  PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -h postgres -U synapse -d synapse -Fc > "$WORK/synapse.pgdump"
  pg_restore --list "$WORK/synapse.pgdump" > "$WORK/restore-manifest.txt"
else
  docker exec army-postgres pg_dump -U synapse -d synapse -Fc > "$WORK/synapse.pgdump"
  docker exec -i army-postgres pg_restore --list < "$WORK/synapse.pgdump" > "$WORK/restore-manifest.txt"
fi
cp -R "$ROOT/.runtime/synapse" "$WORK/synapse"
cp "$ROOT/.runtime/rooms.json" "$WORK/rooms.json"
cp "$ROOT/.runtime/credentials.json" "$WORK/credentials.json"
cp "$ROOT/.runtime/matrix-secrets.json" "$WORK/matrix-secrets.json"
python3 "$ROOT/scripts/backup_mailboxes.py" "$ROOT/.runtime" "$WORK/mailboxes"
for state in "$ROOT"/.runtime/*-state.json; do
  [ ! -e "$state" ] || cp "$state" "$WORK/"
done

tar -C "$ROOT/.runtime/backups" -czf "$ROOT/.runtime/backups/army-hub-$STAMP.tar.gz" "$STAMP"
rm -rf "$WORK"
ls -1t "$ROOT"/.runtime/backups/army-hub-*.tar.gz 2>/dev/null | tail -n +15 | while IFS= read -r archive; do
  [ -n "$archive" ] && rm -f "$archive"
done
echo "Backup verified: army-hub-$STAMP.tar.gz"
