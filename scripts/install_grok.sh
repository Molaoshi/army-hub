#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"

pid_is_live() {
  [ -f "$1" ] && kill -0 "$(cat "$1")" 2>/dev/null
}

if ! pid_is_live "$ROOT/.runtime/grok.pid"; then
  cd "$ROOT/bridge"
  nohup "$ROOT/.venv-service/bin/python" -m army_grok --config "$ROOT/.runtime/grok.yaml" >> "$ROOT/.runtime/grok.log" 2>&1 &
  echo $! > "$ROOT/.runtime/grok.pid"
  cd "$ROOT"
  echo "Started Grok connector."
else
  echo "Grok connector already running."
fi

if ! pid_is_live "$ROOT/.runtime/grok-tunnel.pid"; then
  : > "$ROOT/.runtime/grok-tunnel.log"
  nohup /opt/homebrew/bin/cloudflared tunnel --url http://127.0.0.1:3105 --no-autoupdate >> "$ROOT/.runtime/grok-tunnel.log" 2>&1 &
  echo $! > "$ROOT/.runtime/grok-tunnel.pid"
  echo "Started Grok MCP quick tunnel."
else
  echo "Grok MCP tunnel already running."
fi

"$ROOT/.venv-service/bin/python" - <<'PY'
from pathlib import Path
import re
import time
root = Path.cwd()
log = root / ".runtime/grok-tunnel.log"
for _ in range(45):
    match = re.search(r"https://[-a-z0-9]+\.trycloudflare\.com", log.read_text(errors="replace"))
    if match:
        (root / ".runtime/grok-mcp-base-url").write_text(match.group(0), encoding="utf-8")
        (root / ".runtime/grok-mcp-base-url").chmod(0o600)
        print("Grok MCP public tunnel is ready.")
        break
    time.sleep(1)
else:
    raise SystemExit("Tunnel URL did not appear; inspect .runtime/grok-tunnel.log")
PY
