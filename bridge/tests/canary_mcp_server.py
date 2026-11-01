#!/usr/bin/env python3
"""Dependency-free stdio MCP fixture for the isolated Hermes native canary."""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import sys
from typing import Any

MARKER_V1 = "HERMES-MCP-CANARY-OK"
MARKER_V2 = "HERMES-MCP-CANARY-V2-OK"


def _record(event: str) -> None:
    raw_path = os.environ.get("CANARY_EVENTS_PATH")
    if not raw_path:
        return
    path = Path(raw_path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"event": event}, separators=(",", ":")) + "\n")
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def _tools() -> list[dict[str, Any]]:
    if os.environ.get("CANARY_MODE") == "approval":
        return [{
            "name": "approval_probe",
            "description": "Approval-gated canary probe that must never execute in this acceptance run.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            "annotations": {"readOnlyHint": False},
        }]
    version_two = os.environ.get("CANARY_SCHEMA_VERSION") == "v2"
    properties: dict[str, Any] = {}
    if version_two:
        properties["detail"] = {
            "type": "string",
            "description": "Optional detail added by the v2 schema.",
            "maxLength": 64,
        }
    return [{
        "name": "canary_status",
        "description": "Return the Army Hub canary readiness marker without changing any state.",
        "inputSchema": {
            "type": "object", "properties": properties, "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True},
    }]


def _result(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _text_result(request_id: Any, text: str) -> dict[str, Any]:
    return _result(request_id, {"content": [{"type": "text", "text": text}], "isError": False})


def _handle(request: dict[str, Any]) -> dict[str, Any] | None:
    method = request.get("method")
    request_id = request.get("id")
    if method == "initialize":
        return _result(request_id, {
            "protocolVersion": "2025-03-26",
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "army-hub-native-canary", "version": "1.0.0"},
        })
    if method == "ping":
        return _result(request_id, {})
    if method == "tools/list":
        return _result(request_id, {"tools": _tools()})
    if method == "tools/call":
        params = request.get("params") or {}
        name = params.get("name")
        if name == "canary_status" and os.environ.get("CANARY_MODE") != "approval":
            _record("canary_executed")
            marker = MARKER_V2 if os.environ.get("CANARY_SCHEMA_VERSION") == "v2" else MARKER_V1
            return _text_result(request_id, marker)
        if name == "approval_probe" and os.environ.get("CANARY_MODE") == "approval":
            _record("approval_executed")
            return _text_result(request_id, "APPROVAL-PROBE-UNEXPECTEDLY-EXECUTED")
        return {
            "jsonrpc": "2.0", "id": request_id,
            "error": {"code": -32602, "message": "Unknown canary tool"},
        }
    if request_id is not None:
        return {
            "jsonrpc": "2.0", "id": request_id,
            "error": {"code": -32601, "message": "Method not found"},
        }
    return None


def main() -> None:
    for line in sys.stdin:
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue
        response = _handle(request)
        if response is not None:
            sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
