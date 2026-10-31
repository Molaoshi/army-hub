#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
CONFIG="$ROOT/deploy/grok-supervisord.conf"
PID_FILE="$ROOT/.runtime/grok-supervisord.pid"
CTL="$ROOT/.venv-service/bin/supervisorctl"

if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  "$CTL" -c "$CONFIG" status
  exit 0
fi
rm -f "$ROOT/.runtime/grok-supervisord.sock"
"$ROOT/.venv-service/bin/supervisord" -c "$CONFIG"
"$CTL" -c "$CONFIG" status
