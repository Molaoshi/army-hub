#!/usr/bin/env python3
"""Render the ignored native-gateway connector configuration for secure transfer."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime"
CREDENTIALS = json.loads((RUNTIME / "credentials.json").read_text(encoding="utf-8"))
ROOMS = json.loads((RUNTIME / "rooms.json").read_text(encoding="utf-8"))
record = CREDENTIALS["grok"]
endpoint = (RUNTIME / "grok-gateway-matrix-base-url").read_text(encoding="utf-8").strip()
config = {
    "matrix": {
        "homeserver": endpoint,
        "user_id": record["mxid"],
        "access_token": record["access_token"],
        "device_id": record["device_id"],
        "allowed_users": [CREDENTIALS[name]["mxid"] for name in ("mo", "hermes-mini", "dsh-mini", "grok")],
        "allowed_rooms": [item["room_id"] for item in ROOMS.values()],
    },
    "gateway": {
        "base_url": "http://127.0.0.1:1340",
        "agent_id": "02551c84-3200-462e-a5b0-fcbf87231884",
        "discovery_path": "/home/box/sand-data/gateway.json",
        "reply_timeout_seconds": 600,
        "poll_interval_seconds": 1,
        "stable_reply_seconds": 5,
    },
    "policy": {
        "max_agent_turns": 6,
        "min_turn_interval_seconds": 2,
        "request_timeout_seconds": 30,
        "allow_agent_senders": True,
        "max_message_chars": 40000,
    },
    "state_path": str(RUNTIME / "grok-gateway-state.json"),
}
path = RUNTIME / "grok-gateway.yaml"
path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
path.chmod(0o600)
print("Configured native Grok gateway connector; secrets remain in ignored runtime files.")
