#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PID_FILE="$ROOT/.runtime/agent-manager.pid"
[ -f "$PID_FILE" ] || exit 0
pid=$(cat "$PID_FILE")
command=$(ps -p "$pid" -o command= 2>/dev/null || true)
case "$command" in
  *uvicorn*army_manager.app:app*) kill "$pid" ;;
esac
rm -f "$PID_FILE"
echo "Stopped Agent Manager"
