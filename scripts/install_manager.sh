#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PID_FILE="$ROOT/.runtime/agent-manager.pid"
if [ -f "$PID_FILE" ]; then
  pid=$(cat "$PID_FILE")
  if kill -0 "$pid" 2>/dev/null; then
    echo "Agent Manager already running as PID $pid"
    exit 0
  fi
fi
cd "$ROOT"
nohup "$ROOT/.venv-service/bin/python" -m uvicorn army_manager.app:app \
  --app-dir "$ROOT/manager" --host 127.0.0.1 --port 3104 \
  >> "$ROOT/.runtime/agent-manager.log" 2>&1 &
echo $! > "$PID_FILE"
sleep 1
pid=$(cat "$PID_FILE")
if ! kill -0 "$pid" 2>/dev/null; then
  echo "Agent Manager failed to start; inspect .runtime/agent-manager.log" >&2
  exit 1
fi
echo "Agent Manager running as PID $pid on http://127.0.0.1:3104"
