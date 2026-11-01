from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

FIXTURE = Path(__file__).with_name("canary_mcp_server.py")


def exchange(*messages: dict, environment: dict[str, str] | None = None) -> list[dict]:
    import os

    env = os.environ.copy()
    env.update(environment or {})
    process = subprocess.run(
        [sys.executable, str(FIXTURE)],
        input="".join(json.dumps(message, separators=(",", ":")) + "\n" for message in messages),
        capture_output=True, text=True, timeout=10, check=True, env=env,
    )
    return [json.loads(line) for line in process.stdout.splitlines()]


def request(request_id: int, method: str, params: dict | None = None) -> dict:
    message = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        message["params"] = params
    return message


def test_initialize_and_read_only_tool_discovery():
    responses = exchange(
        request(1, "initialize", {
            "protocolVersion": "2025-03-26", "capabilities": {},
            "clientInfo": {"name": "fixture-test", "version": "1"},
        }),
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        request(2, "tools/list"),
    )
    assert responses[0]["result"]["serverInfo"]["name"] == "army-hub-native-canary"
    tool = responses[1]["result"]["tools"][0]
    assert tool["name"] == "canary_status"
    assert tool["annotations"]["readOnlyHint"] is True
    assert tool["inputSchema"]["properties"] == {}


def test_static_read_only_call_and_schema_change(tmp_path):
    events = tmp_path / "events.jsonl"
    responses = exchange(
        request(1, "tools/call", {"name": "canary_status", "arguments": {}}),
        environment={"CANARY_EVENTS_PATH": str(events)},
    )
    assert responses[0]["result"]["content"][0]["text"] == "HERMES-MCP-CANARY-OK"
    assert json.loads(events.read_text()) == {"event": "canary_executed"}

    changed = exchange(
        request(2, "tools/list"),
        request(3, "tools/call", {"name": "canary_status", "arguments": {"detail": "v2"}}),
        environment={"CANARY_SCHEMA_VERSION": "v2"},
    )
    assert "detail" in changed[0]["result"]["tools"][0]["inputSchema"]["properties"]
    assert changed[1]["result"]["content"][0]["text"] == "HERMES-MCP-CANARY-V2-OK"


def test_approval_fixture_is_distinct_and_records_if_it_ever_executes(tmp_path):
    events = tmp_path / "events.jsonl"
    responses = exchange(
        request(1, "tools/list"),
        request(2, "tools/call", {"name": "approval_probe", "arguments": {}}),
        environment={"CANARY_MODE": "approval", "CANARY_EVENTS_PATH": str(events)},
    )
    tool = responses[0]["result"]["tools"][0]
    assert tool["name"] == "approval_probe"
    assert tool["annotations"]["readOnlyHint"] is False
    assert responses[1]["result"]["content"][0]["text"] == "APPROVAL-PROBE-UNEXPECTEDLY-EXECUTED"
    assert json.loads(events.read_text()) == {"event": "approval_executed"}
