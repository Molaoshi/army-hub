#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
file="$ROOT/.runtime/grok-gateway-matrix-tunnel.pid"
if [ -f "$file" ]; then
  pid=$(cat "$file")
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid"
  fi
  rm -f "$file"
fi
