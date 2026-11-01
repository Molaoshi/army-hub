#!/usr/bin/env python3
"""Render the ignored Grok connector configuration from provisioned secrets."""

from __future__ import annotations

import json
from pathlib import Path
import secrets

import yaml

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime"
CREDENTIALS = json.loads((RUNTIME / "credentials.json").read_text(encoding="utf-8"))
ROOMS = json.loads((RUNTIME / "rooms.json").read_text(encoding="utf-8"))
record = CREDENTIALS["grok"]
endpoint = (RUNTIME / "grok-webhook-endpoint").read_text(encoding="utf-8").strip()
if not endpoint.startswith("https://"):
    endpoint = "https://" + endpoint.lstrip("/")
secret_path = RUNTIME / "grok-mcp-path-secret"
if not secret_path.exists():
    secret_path.write_text(secrets.token_urlsafe(32), encoding="utf-8")
secret_path.chmod(0o600)
config = {
    "matrix": {
        "homeserver": "http://127.0.0.1:8010",
        "user_id": record["mxid"],
        "access_token": record["access_token"],
        "device_id": record["device_id"],
        "allowed_users": [CREDENTIALS[name]["mxid"] for name in ("mo", "hermes-mini", "dsh-mini", "grok")],
        "allowed_rooms": [item["room_id"] for item in ROOMS.values()],
    },
    "grok": {
        "webhook_url": endpoint,
        "signing_secret": (RUNTIME / "grok-webhook-signing-secret").read_text(encoding="utf-8").strip(),
        "mcp_path_secret": secret_path.read_text(encoding="utf-8").strip(),
        "reply_token_ttl_seconds": 1800,
    },
    "policy": {
        "max_agent_turns": 6,
        "min_turn_interval_seconds": 2,
        "request_timeout_seconds": 30,
        "allow_agent_senders": True,
        "max_message_chars": 40000,
    },
    "state_path": str(RUNTIME / "grok-state.json"),
    "host": "127.0.0.1",
    "port": 3105,
}
path = RUNTIME / "grok.yaml"
path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
path.chmod(0o600)
print("Configured Grok connector; secrets remain in ignored runtime files.")
