#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
for name in grok-tunnel grok; do
  file="$ROOT/.runtime/$name.pid"
  if [ -f "$file" ]; then
    pid=$(cat "$file")
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid"
    fi
    rm -f "$file"
  fi
done
