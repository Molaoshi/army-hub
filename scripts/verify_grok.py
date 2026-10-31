#!/usr/bin/env python3
"""Live acceptance for the real Grok webhook/MCP Matrix loop."""

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
PROTOCOL_KEY = "com.molaoshi.army_hub"
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


def send(sender: str, body: str, *, agent_turn: int | None = None) -> str:
    content: dict = {"msgtype": "m.text", "body": body, "m.mentions": {"user_ids": [GROK] if "@grok" in body else []}}
    if agent_turn is not None:
        content[PROTOCOL_KEY] = {"agent_turn": agent_turn, "agent_id": sender}
    txn = uuid.uuid4().hex
    path = f"/_matrix/client/v3/rooms/{urllib.parse.quote(ROOM_ID, safe='')}/send/m.room.message/{txn}"
    return request("PUT", path, CREDENTIALS[sender]["access_token"], content)["event_id"]


def recent() -> list[dict]:
    path = f"/_matrix/client/v3/rooms/{urllib.parse.quote(ROOM_ID, safe='')}/messages?dir=b&limit=100"
    return request("GET", path, CREDENTIALS["mo"]["access_token"])["chunk"]


def matching(root: str, msgtype: str, after_ms: int, sender: str = GROK) -> list[dict]:
    matches = []
    for event in recent():
        relation = event.get("content", {}).get("m.relates_to", {})
        event_root = relation.get("event_id") if relation.get("rel_type") == "m.thread" else event["event_id"]
        if event.get("origin_server_ts", 0) >= after_ms and event.get("sender") == sender and event.get("content", {}).get("msgtype") == msgtype and event_root == root:
            matches.append(event)
    return matches


def wait_for(root: str, msgtype: str, after_ms: int, timeout: int = 240, sender: str = GROK) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        events = matching(root, msgtype, after_ms, sender)
        if events:
            return events[0]
        time.sleep(2)
    raise TimeoutError(f"No {msgtype} from {sender} in thread {root} within {timeout} seconds")


def capture_reply_token(root: str, timeout: int = 60) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state_path = RUNTIME / "grok-state.json"
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8"))
            for token, record in state.get("pending_replies", {}).items():
                if record.get("reply_to") == root:
                    return token
        time.sleep(1)
    raise TimeoutError("No pending Grok reply token was persisted")


def record(name: str, detail: str) -> None:
    RESULTS.append({"test": name, "status": "passed", "detail": detail})
    print(f"PASS: {name} — {detail}", flush=True)
    (RUNTIME / "grok-verification-results.json").write_text(json.dumps(RESULTS, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    started = int(time.time() * 1000)
    marker = uuid.uuid4().hex[:10]

    quiet_root = send("mo", f"Unmentioned Grok connector probe; do not answer. QUIET-{marker}")
    time.sleep(15)
    if matching(quiet_root, "m.text", started):
        raise AssertionError("Grok answered without an explicit mention")
    record("unmentioned silence", quiet_root)

    root = send("mo", f"@grok Reply once with exactly GROK-ARMY-OK-{marker}; no other work.")
    reply_token = capture_reply_token(root)
    reply = wait_for(root, "m.text", started)
    if marker not in reply["content"].get("body", ""):
        raise AssertionError("Grok reply did not contain the unique acceptance marker")
    if reply["content"].get(PROTOCOL_KEY, {}).get("agent_turn") != 1:
        raise AssertionError("Grok reply did not preserve the agent-turn protocol")
    record("real Grok mention, MCP reply, and thread", reply["event_id"])

    mcp_url = (RUNTIME / "grok-mcp-url").read_text(encoding="utf-8").strip()
    duplicate = json.dumps({
        "jsonrpc": "2.0", "id": "duplicate-check", "method": "tools/call",
        "params": {"name": "army_reply", "arguments": {"reply_token": reply_token, "text": "duplicate must not be posted"}},
    }).encode()
    req = urllib.request.Request(mcp_url, data=duplicate, headers={"content-type": "application/json", "accept": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as response:
        duplicate_result = json.loads(response.read())
    if duplicate_result.get("result", {}).get("isError") is not True:
        raise AssertionError("A used reply token was accepted twice")
    record("single-use callback token", "duplicate rejected")

    handoff_root = send(
        "hermes-mini",
        f"@grok Reply once with HANDOFF-{marker} @hermes-mini so Hermes can acknowledge; no other work.",
        agent_turn=1,
    )
    handoff_reply = wait_for(handoff_root, "m.text", started)
    if marker not in handoff_reply["content"].get("body", "") or "@hermes-mini" not in handoff_reply["content"].get("body", ""):
        raise AssertionError("Grok did not complete the explicit return handoff")
    hermes = CREDENTIALS["hermes-mini"]["mxid"]
    hermes_ack = wait_for(handoff_root, "m.text", started, sender=hermes)
    record("Hermes to Grok to Hermes handoff", f"Grok={handoff_reply['event_id']}; Hermes={hermes_ack['event_id']}")

    budget_root = send("hermes-mini", f"@grok Budget probe BUDGET-{marker}", agent_turn=6)
    notice = wait_for(budget_root, "m.notice", started, timeout=45)
    time.sleep(5)
    if matching(budget_root, "m.text", started):
        raise AssertionError("Grok ran after the agent-turn budget was exhausted")
    record("six-turn budget stop", notice["event_id"])
    print(f"All {len(RESULTS)} live Grok acceptance tests passed.", flush=True)


if __name__ == "__main__":
    main()
