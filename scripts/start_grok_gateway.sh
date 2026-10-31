#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

pid_is_live() {
  [ -f "$1" ] && kill -0 "$(cat "$1")" 2>/dev/null
}

if pid_is_live "$ROOT/.runtime/grok-supervisord.pid"; then
  config="$ROOT/deploy/grok-supervisord.conf"
  ctl="$ROOT/.venv-service/bin/supervisorctl"
  status=$("$ctl" -c "$config" status army-grok)
  case "$status" in
    *RUNNING*)
      echo "Native Grok gateway connector is already supervised and running."
      exit 0
      ;;
  esac
  exec "$ctl" -c "$config" start army-grok
fi

if pid_is_live "$ROOT/.runtime/grok.pid"; then
  echo "Refusing to start: legacy Grok connector is still running." >&2
  exit 1
fi
if pid_is_live "$ROOT/.runtime/grok-gateway.pid"; then
  echo "Native Grok gateway connector already running."
  exit 0
fi
cd "$ROOT/bridge"
nohup "$ROOT/.venv-service/bin/python" -m army_grok_gateway --config "$ROOT/.runtime/grok-gateway.yaml" >> "$ROOT/.runtime/grok-gateway.log" 2>&1 &
echo $! > "$ROOT/.runtime/grok-gateway.pid"
echo "Started native Grok gateway connector."
