#!/usr/bin/env python3
"""Render ignored runtime bridge and launchd configurations from provisioned credentials."""

from __future__ import annotations

import json
import os
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime"
WORKSPACE = ROOT.parent
CREDENTIALS = json.loads((RUNTIME / "credentials.json").read_text(encoding="utf-8"))
ROOMS = json.loads((RUNTIME / "rooms.json").read_text(encoding="utf-8"))
ALLOWED_USERS = [CREDENTIALS[name]["mxid"] for name in ("mo", "hermes-mini", "dsh-mini")]
ALLOWED_ROOMS = [record["room_id"] for record in ROOMS.values()]
LAUNCHD_TEMPLATE = (ROOT / "launchd" / "agent.plist").read_text(encoding="utf-8")

for agent_id, harness in (("hermes-mini", "hermes"), ("dsh-mini", "dsh")):
    if harness == "hermes":
        command = [str(Path.home() / ".local" / "bin" / "hermes"), "acp"]
        environment = {"HERMES_ACCEPT_HOOKS": "1"}
    else:
        command = [str(WORKSPACE / ".runtime" / "dsh-acp.sh")]
        environment = {"NO_BROWSER": "1"}
    record = CREDENTIALS[agent_id]
    config = {
        "matrix": {
            "homeserver": "http://127.0.0.1:8010",
            "user_id": record["mxid"],
            "access_token": record["access_token"],
            "device_id": record["device_id"],
            "allowed_users": ALLOWED_USERS,
            "allowed_rooms": ALLOWED_ROOMS,
        },
        "agent": {
            "id": agent_id,
            "display_name": "Hermes Mini" if harness == "hermes" else "DSH Mini",
            "command": command,
            "cwd": str(WORKSPACE),
            "environment": environment,
        },
        "policy": {
            "max_agent_turns": 6,
            "min_turn_interval_seconds": 2,
            "prompt_timeout_seconds": 600,
            "allow_agent_senders": True,
            "max_message_chars": 40000,
        },
        "state_path": str(RUNTIME / f"{agent_id}-state.json"),
    }
    config_path = RUNTIME / f"{agent_id}.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    config_path.chmod(0o600)

    launchd_dir = RUNTIME / "launchd"
    launchd_dir.mkdir(exist_ok=True)
    rendered = LAUNCHD_TEMPLATE.replace("__ROOT__", str(ROOT)).replace("__AGENT_ID__", agent_id)
    (launchd_dir / f"ai.army.{agent_id}.plist").write_text(rendered, encoding="utf-8")
    print(f"Configured {agent_id}")
