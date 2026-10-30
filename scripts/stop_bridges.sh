#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
UID_VALUE=$(id -u)
for agent in hermes-mini dsh-mini; do
  launchctl bootout "gui/$UID_VALUE/ai.army.$agent" 2>/dev/null || true
  pid_file="$ROOT/.runtime/$agent.pid"
  [ -f "$pid_file" ] || continue
  pid=$(cat "$pid_file")
  command=$(ps -p "$pid" -o command= 2>/dev/null || true)
  case "$command" in
    *army_bridge*"$agent.yaml"*) kill "$pid" ;;
  esac
  rm -f "$pid_file"
  echo "Stopped $agent"
done
