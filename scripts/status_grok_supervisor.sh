#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
CONFIG="$ROOT/deploy/grok-supervisord.conf"
"$ROOT/.venv-service/bin/supervisorctl" -c "$CONFIG" status
if command -v tailscale >/dev/null 2>&1; then
  tailscale status
fi
