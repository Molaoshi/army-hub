from __future__ import annotations

import asyncio
import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Awaitable, Callable

LOG = logging.getLogger(__name__)
ReplyCallback = Callable[[str, str], Awaitable[dict[str, Any]]]


class MCPApplication:
    def __init__(self, path_secret: str):
        self.path = f"/{path_secret}/mcp"
        self.reply_callback: ReplyCallback | None = None
        self.loop: asyncio.AbstractEventLoop | None = None

    def handle(self, path: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any] | None]:
        if path != self.path:
            return 404, {"error": "not_found"}
        method = payload.get("method")
        request_id = payload.get("id")
        if method == "initialize":
            requested = payload.get("params", {}).get("protocolVersion", "2025-03-26")
            return 200, self._result(request_id, {
                "protocolVersion": requested,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "army-hub-grok", "version": "1.0.0"},
                "instructions": "Use army_reply only to answer the Matrix delivery identified by reply_token.",
            })
        if method == "ping":
            return 200, self._result(request_id, {})
        if method == "notifications/initialized":
            return 202, None
        if method == "tools/list":
            return 200, self._result(request_id, {"tools": [{
                "name": "army_reply",
                "description": "Deliver Grok's answer to the originating Army Hub Matrix thread. The reply token authorizes one response to one event and expires shortly.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "reply_token": {"type": "string", "description": "The reply_token supplied in the Matrix webhook payload."},
                        "text": {"type": "string", "description": "The final concise answer to post in Matrix.", "minLength": 1, "maxLength": 40000},
                    },
                    "required": ["reply_token", "text"],
                    "additionalProperties": False,
                },
            }]})
        if method == "tools/call":
            return self._call_tool(request_id, payload.get("params", {}))
        if request_id is None:
            return 202, None
        return 200, {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "method_not_found"}}

    def _call_tool(self, request_id: Any, params: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        if params.get("name") != "army_reply":
            return 200, self._error_result(request_id, "unknown_tool")
        arguments = params.get("arguments", {})
        token = arguments.get("reply_token")
        text = arguments.get("text")
        if not isinstance(token, str) or not isinstance(text, str) or not text.strip() or len(text) > 40_000:
            return 200, self._error_result(request_id, "valid reply_token and non-empty text up to 40000 characters are required")
        if not self.loop or not self.reply_callback:
            return 200, self._error_result(request_id, "connector_not_ready")
        future = asyncio.run_coroutine_threadsafe(self.reply_callback(token, text), self.loop)
        try:
            result = future.result(timeout=20)
            return 200, self._result(request_id, {
                "content": [{"type": "text", "text": f"Matrix reply delivered as {result['event_id']}."}],
                "structuredContent": result,
            })
        except Exception as error:
            LOG.warning("MCP reply rejected: %s", str(error)[:160])
            return 200, self._error_result(request_id, str(error)[:300])

    @staticmethod
    def _result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def _error_result(self, request_id: Any, message: str) -> dict[str, Any]:
        return self._result(request_id, {"content": [{"type": "text", "text": message}], "isError": True})


class MCPServer:
    def __init__(self, host: str, port: int, path_secret: str):
        self.application = MCPApplication(path_secret)
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                try:
                    length = int(self.headers.get("content-length", "0"))
                    if length <= 0 or length > 1_048_576:
                        self._reply(413, {"error": "invalid_body_size"})
                        return
                    payload = json.loads(self.rfile.read(length))
                    if not isinstance(payload, dict):
                        raise ValueError("object required")
                    status, response = outer.application.handle(self.path, payload)
                    self._reply(status, response)
                except (ValueError, json.JSONDecodeError):
                    self._reply(400, {"error": "invalid_json"})

            def do_GET(self) -> None:
                self._reply(405, {"error": "stream_not_supported"})

            def _reply(self, status: int, payload: dict[str, Any] | None) -> None:
                if payload is None:
                    self.send_response(status)
                    self.end_headers()
                    return
                body = json.dumps(payload, separators=(",", ":")).encode()
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: Any) -> None:
                LOG.info("MCP HTTP %s", args[1] if len(args) > 1 else "request")

        self.httpd = ThreadingHTTPServer((host, port), Handler)
        self.httpd.daemon_threads = True

    def start(self, callback: ReplyCallback, loop: asyncio.AbstractEventLoop) -> None:
        import threading

        self.application.reply_callback = callback
        self.application.loop = loop
        threading.Thread(target=self.httpd.serve_forever, name="grok-mcp", daemon=True).start()

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
