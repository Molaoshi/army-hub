#!/usr/bin/env python3
"""Invite and join the reserved Grok identity to the approved Army Hub rooms."""

from __future__ import annotations

import json
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime"
BASE = "http://127.0.0.1:8010"
CREDENTIALS = json.loads((RUNTIME / "credentials.json").read_text(encoding="utf-8"))
ROOMS = json.loads((RUNTIME / "rooms.json").read_text(encoding="utf-8"))
GROK = CREDENTIALS["grok"]["mxid"]


def post(path: str, token: str, body: dict) -> None:
    request = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30):
            return
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")
        if error.code == 403 and "already" in detail:
            return
        raise RuntimeError(f"Matrix enrollment failed: {error.code} {detail}") from error


for name, record in ROOMS.items():
    room = urllib.parse.quote(record["room_id"], safe="")
    post(f"/_matrix/client/v3/rooms/{room}/invite", CREDENTIALS["mo"]["access_token"], {"user_id": GROK})
    post(f"/_matrix/client/v3/rooms/{room}/join", CREDENTIALS["grok"]["access_token"], {})
    print(f"Grok joined {name}")
