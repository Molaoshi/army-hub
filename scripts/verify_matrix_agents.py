#!/usr/bin/env python3
"""Exercise live Matrix mention, threading, handoff, and anti-loop behavior."""

from __future__ import annotations

import json
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime"
BASE = "http://127.0.0.1:8010"
PROTOCOL_KEY = "com.molaoshi.army_hub"
CREDENTIALS = json.loads((RUNTIME / "credentials.json").read_text(encoding="utf-8"))
ROOM_ID = json.loads((RUNTIME / "rooms.json").read_text(encoding="utf-8"))["army-lab"]["room_id"]
MO = CREDENTIALS["mo"]["mxid"]
AGENTS = {name: CREDENTIALS[name]["mxid"] for name in ("hermes-mini", "dsh-mini")}
RESULTS: list[dict] = []


def request(method: str, path: str, token: str, body: dict | None = None) -> dict:
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"{method} {path}: {error.code} {error.read().decode(errors='replace')}") from error


def send(sender: str, body: str, *, root: str | None = None, agent_turn: int | None = None) -> str:
    content: dict = {
        "msgtype": "m.text",
        "body": body,
        "m.mentions": {"user_ids": [mxid for name, mxid in AGENTS.items() if f"@{name}" in body]},
    }
    if root:
        content["m.relates_to"] = {
            "rel_type": "m.thread",
            "event_id": root,
            "is_falling_back": True,
            "m.in_reply_to": {"event_id": root},
        }
    if agent_turn is not None:
        content[PROTOCOL_KEY] = {"agent_turn": agent_turn, "agent_id": sender}
    txn = uuid.uuid4().hex
    path = f"/_matrix/client/v3/rooms/{urllib.parse.quote(ROOM_ID, safe='')}/send/m.room.message/{txn}"
    return request("PUT", path, CREDENTIALS[sender]["access_token"], content)["event_id"]


def recent() -> list[dict]:
    path = f"/_matrix/client/v3/rooms/{urllib.parse.quote(ROOM_ID, safe='')}/messages?dir=b&limit=200"
    return request("GET", path, CREDENTIALS["mo"]["access_token"])["chunk"]


def thread_root(event: dict) -> str:
    relation = event.get("content", {}).get("m.relates_to", {})
    return relation.get("event_id") if relation.get("rel_type") == "m.thread" else event["event_id"]


def matching(root: str, sender: str, msgtype: str, after_ms: int) -> list[dict]:
    return [
        event for event in recent()
        if event.get("origin_server_ts", 0) >= after_ms
        and event.get("sender") == AGENTS.get(sender, MO if sender == "mo" else sender)
        and event.get("content", {}).get("msgtype") == msgtype
        and thread_root(event) == root
    ]


def wait_for(root: str, sender: str, msgtype: str, after_ms: int, timeout: int = 240) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        events = matching(root, sender, msgtype, after_ms)
        if events:
            return events[0]
        time.sleep(2)
    raise TimeoutError(f"No {msgtype} from {sender} in thread {root} within {timeout} seconds")


def record(name: str, detail: str) -> None:
    RESULTS.append({"test": name, "status": "passed", "detail": detail})
    print(f"PASS: {name} — {detail}", flush=True)
    (RUNTIME / "verification-results.json").write_text(json.dumps(RESULTS, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    started = int(time.time() * 1000)
    marker = uuid.uuid4().hex[:10]

    quiet_root = send("mo", f"Routine unmentioned note; do not answer. QUIET-{marker}")
    time.sleep(15)
    replies = [event for sender in AGENTS for event in matching(quiet_root, sender, "m.text", started)]
    if replies:
        raise AssertionError("An agent answered a message without an explicit mention")
    record("unmentioned silence", quiet_root)

    hermes_root = send("mo", f"@hermes-mini Reply once with exactly HERMES-OK-{marker}; no other work.")
    hermes_reply = wait_for(hermes_root, "hermes-mini", "m.text", started)
    record("Hermes mention and thread", hermes_reply["event_id"])

    dsh_root = send("mo", f"@dsh-mini Reply once with exactly DSH-OK-{marker}; no other work.")
    dsh_reply = wait_for(dsh_root, "dsh-mini", "m.text", started)
    record("DSH mention and thread", dsh_reply["event_id"])

    handoff_root = send(
        "hermes-mini",
        f"@dsh-mini Reply once with exactly HANDOFF-{marker} @hermes-mini so Hermes can acknowledge; no other work.",
    )
    handoff_reply = wait_for(handoff_root, "dsh-mini", "m.text", started)
    if "@hermes-mini" not in handoff_reply["content"].get("body", ""):
        raise AssertionError("DSH did not explicitly mention Hermes for the return handoff")
    hermes_ack = wait_for(handoff_root, "hermes-mini", "m.text", started)
    record("agent-to-agent handoff", f"DSH={handoff_reply['event_id']}; Hermes={hermes_ack['event_id']}")

    budget_root = send("hermes-mini", f"@dsh-mini Budget probe BUDGET-{marker}", agent_turn=6)
    notice = wait_for(budget_root, "dsh-mini", "m.notice", started, timeout=45)
    time.sleep(5)
    if matching(budget_root, "dsh-mini", "m.text", started):
        raise AssertionError("A model turn ran after the agent budget was exhausted")
    record("six-turn budget stop", notice["event_id"])

    print(f"All {len(RESULTS)} live Matrix acceptance tests passed.", flush=True)


if __name__ == "__main__":
    main()
