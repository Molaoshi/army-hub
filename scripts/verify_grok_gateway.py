#!/usr/bin/env python3
"""Live two-turn memory acceptance for the persistent native Grok connector."""

from __future__ import annotations

import json
from pathlib import Path
import time
import urllib.parse
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime"
BASE = "http://127.0.0.1:8010"
CREDENTIALS = json.loads((RUNTIME / "credentials.json").read_text(encoding="utf-8"))
ROOM_ID = json.loads((RUNTIME / "rooms.json").read_text(encoding="utf-8"))["army-lab"]["room_id"]
GROK = CREDENTIALS["grok"]["mxid"]
RESULTS: list[dict] = []


def request(method: str, path: str, token: str, body: dict | None = None) -> dict:
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as response:
        raw = response.read()
        return json.loads(raw) if raw else {}


def send(body: str) -> str:
    content = {"msgtype": "m.text", "body": body, "m.mentions": {"user_ids": [GROK] if "@grok" in body else []}}
    txn = uuid.uuid4().hex
    path = f"/_matrix/client/v3/rooms/{urllib.parse.quote(ROOM_ID, safe='')}/send/m.room.message/{txn}"
    return request("PUT", path, CREDENTIALS["mo"]["access_token"], content)["event_id"]


def recent() -> list[dict]:
    path = f"/_matrix/client/v3/rooms/{urllib.parse.quote(ROOM_ID, safe='')}/messages?dir=b&limit=100"
    return request("GET", path, CREDENTIALS["mo"]["access_token"])["chunk"]


def replies(root: str, after_ms: int) -> list[dict]:
    matches = []
    for event in recent():
        content = event.get("content", {})
        relation = content.get("m.relates_to", {})
        if (
            event.get("origin_server_ts", 0) >= after_ms
            and event.get("sender") == GROK
            and content.get("msgtype") == "m.text"
            and relation.get("rel_type") == "m.thread"
            and relation.get("event_id") == root
        ):
            matches.append(event)
    return matches


def wait_for(root: str, after_ms: int, timeout: int = 240) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        events = replies(root, after_ms)
        if events:
            return events[0]
        time.sleep(2)
    raise TimeoutError(f"No threaded native Grok reply for {root} within {timeout} seconds")


def record(name: str, detail: str) -> None:
    RESULTS.append({"test": name, "status": "passed", "detail": detail})
    print(f"PASS: {name} — {detail}", flush=True)
    (RUNTIME / "grok-gateway-verification-results.json").write_text(json.dumps(RESULTS, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    started = int(time.time() * 1000)
    marker = f"ARMY-MEMORY-{uuid.uuid4().hex[:12]}"
    quiet_root = send(f"Unmentioned native Grok probe; do not answer. QUIET-{marker}")
    time.sleep(15)
    if replies(quiet_root, started):
        raise AssertionError("Native Grok answered without an explicit mention")
    record("unmentioned silence", quiet_root)

    first_root = send(f"@grok Remember this exact marker for our next exchange: {marker}. Reply only that you will remember it.")
    first_reply = wait_for(first_root, started)
    record("first persistent Matrix turn", first_reply["event_id"])

    second_root = send("@grok What exact marker did I ask you to remember in my previous Matrix message? Reply with the marker only.")
    second_reply = wait_for(second_root, started)
    body = second_reply["content"].get("body", "")
    if marker not in body:
        raise AssertionError(f"Second-turn reply did not recover the exact marker: {body}")
    record("exact previous-message memory", marker)
    record("two-turn native Matrix proof", f"first={first_root}; second={second_root}; reply={second_reply['event_id']}")
    print("Persistent native Grok memory acceptance passed.", flush=True)


if __name__ == "__main__":
    main()
