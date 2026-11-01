#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
supervisor_pid="$ROOT/.runtime/grok-supervisord.pid"
if [ -f "$supervisor_pid" ] && kill -0 "$(cat "$supervisor_pid")" 2>/dev/null; then
  "$ROOT/.venv-service/bin/supervisorctl" -c "$ROOT/deploy/grok-supervisord.conf" stop army-grok >/dev/null 2>&1 || true
  echo "Stopped supervised native Grok gateway connector."
  exit 0
fi
file="$ROOT/.runtime/grok-gateway.pid"
if [ -f "$file" ]; then
  pid=$(cat "$file")
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid"
  fi
  rm -f "$file"
fi
