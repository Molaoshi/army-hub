#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
UID_VALUE=$(id -u)
cd "$ROOT/bridge"
for agent in hermes-mini dsh-mini; do
  launchctl bootout "gui/$UID_VALUE/ai.army.$agent" 2>/dev/null || true
  pid_file="$ROOT/.runtime/$agent.pid"
  if [ -f "$pid_file" ]; then
    pid=$(cat "$pid_file")
    if kill -0 "$pid" 2>/dev/null; then
      echo "$agent already running as PID $pid"
      continue
    fi
  fi
  nohup "$ROOT/.venv-service/bin/python" -m army_bridge --config "$ROOT/.runtime/$agent.yaml" >> "$ROOT/.runtime/$agent.log" 2>&1 &
  echo $! > "$pid_file"
  echo "Started $agent as PID $!"
done
