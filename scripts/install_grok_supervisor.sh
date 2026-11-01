#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

if [ "$(uname -s)" != "Linux" ]; then
  echo "This installer is for Grok Bot's Linux computer." >&2
  exit 1
fi
if ! sudo -n true 2>/dev/null; then
  echo "Passwordless sudo is required to install and supervise tailscaled." >&2
  exit 1
fi
if ! command -v tailscale >/dev/null 2>&1 || ! command -v tailscaled >/dev/null 2>&1; then
  sudo -n apt-get update
  sudo -n env DEBIAN_FRONTEND=noninteractive apt-get install -y tailscale
fi
if [ ! -x "$ROOT/.venv-service/bin/supervisord" ]; then
  "$ROOT/.venv-service/bin/python" -m pip install 'supervisor>=4.2,<5'
fi

# Prevent the former nohup connector from running beside its supervised replacement.
sh "$ROOT/scripts/stop_grok_gateway.sh"
mkdir -p "$HOME/.config/autostart"
install -m 644 "$ROOT/deploy/army-hub-grok.desktop" "$HOME/.config/autostart/army-hub-grok.desktop"
sh "$ROOT/scripts/start_grok_supervisor.sh"
echo "Installed desktop-login startup and supervised Tailscale/Grok processes."
echo "If Tailscale is not yet enrolled, run: sudo tailscale up --hostname=grok-bot"
