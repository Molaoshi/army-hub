#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
pid_file="$ROOT/.runtime/grok-gateway-matrix-tunnel.pid"
if [ -f "$pid_file" ] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
  echo "Matrix connector tunnel already running."
  exit 0
fi
: > "$ROOT/.runtime/grok-gateway-matrix-tunnel.log"
nohup /opt/homebrew/bin/cloudflared tunnel --url http://127.0.0.1:8010 --no-autoupdate >> "$ROOT/.runtime/grok-gateway-matrix-tunnel.log" 2>&1 &
echo $! > "$pid_file"
"$ROOT/.venv-service/bin/python" - <<'PY'
from pathlib import Path
import re
import time
root = Path.cwd()
log = root / ".runtime/grok-gateway-matrix-tunnel.log"
for _ in range(45):
    match = re.search(r"https://[-a-z0-9]+\.trycloudflare\.com", log.read_text(errors="replace"))
    if match:
        path = root / ".runtime/grok-gateway-matrix-base-url"
        path.write_text(match.group(0), encoding="utf-8")
        path.chmod(0o600)
        print("Authenticated Matrix connector tunnel is ready.")
        break
    time.sleep(1)
else:
    raise SystemExit("Tunnel URL did not appear; inspect the ignored tunnel log")
PY
