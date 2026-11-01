from __future__ import annotations

from army_grok.mcp import MCPApplication


def test_mcp_discovery_exposes_only_single_reply_tool() -> None:
    app = MCPApplication("secret-path")
    status, initialized = app.handle(app.path, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}})
    assert status == 200
    assert initialized["result"]["protocolVersion"] == "2025-06-18"
    status, listing = app.handle(app.path, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    tools = listing["result"]["tools"]
    assert [tool["name"] for tool in tools] == ["army_reply"]
    assert tools[0]["inputSchema"]["required"] == ["reply_token", "text"]


def test_mcp_rejects_wrong_path_and_invalid_reply() -> None:
    app = MCPApplication("secret-path")
    status, _ = app.handle("/wrong", {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert status == 404
    status, response = app.handle(app.path, {
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "army_reply", "arguments": {"reply_token": "x", "text": ""}},
    })
    assert status == 200
    assert response["result"]["isError"] is True
