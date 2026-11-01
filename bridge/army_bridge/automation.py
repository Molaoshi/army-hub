from __future__ import annotations

import asyncio
import hmac
import json
import re
import secrets
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit, unquote
from uuid import uuid4

from .config import AgentSettings, AutomationSettings
from .mailbox import AutomationRateLimit, DeliveryStateError, DurableMailbox, IdempotencyConflict


CONVERSATION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class HttpError(RuntimeError):
    def __init__(self, status: int, message: str, headers: dict[str, str] | None = None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.headers = headers or {}


class AutomationServer:
    """Per-agent loopback API. The token file proves the caller is this OS user."""

    def __init__(
        self,
        *,
        settings: AutomationSettings,
        agent: AgentSettings,
        mailbox: DurableMailbox,
        on_enqueue: Callable[[], None],
    ):
        self.settings = settings
        self.agent = agent
        self.mailbox = mailbox
        self.on_enqueue = on_enqueue
        self.server: asyncio.AbstractServer | None = None
        self.port = 0
        self.token = ""
        self.files: list[Path] = []

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}" if self.port else ""

    async def start(self) -> None:
        if not self.settings.enabled or self.server is not None:
            return
        if self.settings.state_dir is None:
            raise RuntimeError("automation state_dir is required when the API is enabled")
        root = self.settings.state_dir
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        root.chmod(0o700)
        self.token = secrets.token_urlsafe(32)
        self.server = await asyncio.start_server(self._handle_client, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]
        self.files = [root / "url", root / "token", root / "headers"]
        self._write_secret(root / "url", self.url + "\n", secret=False)
        self._write_secret(root / "token", self.token + "\n")
        self._write_secret(root / "headers", f"Authorization: Bearer {self.token}\n")

    @staticmethod
    def _write_secret(path: Path, content: str, secret: bool = True) -> None:
        path.write_text(content, encoding="utf-8")
        path.chmod(0o600)

    async def stop(self) -> None:
        server = self.server
        self.server = None
        self.port = 0
        self.token = ""
        if server is not None:
            server.close()
            await server.wait_closed()
        for path in self.files:
            path.unlink(missing_ok=True)
        self.files = []

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            method, target, headers, body = await asyncio.wait_for(self._read_request(reader), timeout=10)
            if headers.get("host") != f"127.0.0.1:{self.port}" or "origin" in headers:
                raise HttpError(403, "forbidden")
            expected = f"Bearer {self.token}"
            if not hmac.compare_digest(headers.get("authorization", ""), expected):
                raise HttpError(401, "unauthorized")
            status, payload = await self._route(method, target, headers, body)
        except HttpError as error:
            status, payload = error.status, {"error": error.message}
            extra_headers = error.headers
        except Exception:
            status, payload = 500, {"error": "internal server error"}
            extra_headers = {}
        else:
            extra_headers = {}
        await self._send_json(writer, status, payload, extra_headers)

    async def _read_request(
        self, reader: asyncio.StreamReader
    ) -> tuple[str, str, dict[str, str], bytes]:
        request_line = await reader.readline()
        if not request_line or len(request_line) > 8192:
            raise HttpError(400, "invalid request")
        try:
            method, target, version = request_line.decode("ascii").strip().split(" ")
        except (UnicodeDecodeError, ValueError):
            raise HttpError(400, "invalid request") from None
        if version != "HTTP/1.1":
            raise HttpError(400, "HTTP/1.1 is required")

        headers: dict[str, str] = {}
        for _ in range(100):
            line = await reader.readline()
            if line in {b"\r\n", b"\n"}:
                break
            if not line or len(line) > 16_384:
                raise HttpError(400, "invalid headers")
            try:
                name, value = line.decode("latin-1").split(":", 1)
            except ValueError:
                raise HttpError(400, "invalid headers") from None
            name = name.strip().lower()
            if name in {"host", "origin", "authorization", "content-length"} and name in headers:
                raise HttpError(400, "duplicate header")
            headers[name] = value.strip()
        else:
            raise HttpError(400, "too many headers")
        if "transfer-encoding" in headers:
            raise HttpError(400, "transfer encoding is not supported")
        try:
            length = int(headers.get("content-length", "0"))
        except ValueError:
            raise HttpError(400, "invalid content length") from None
        if length < 0:
            raise HttpError(400, "invalid content length")
        if length > self.settings.body_limit_bytes:
            raise HttpError(413, "request body is too large")
        body = await reader.readexactly(length) if length else b""
        return method.upper(), target, headers, body

    async def _route(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> tuple[int, dict[str, Any]]:
        path = urlsplit(target).path
        parts = [unquote(part) for part in path.split("/") if part]
        if parts == ["v1", "agents"]:
            if method != "GET":
                raise HttpError(405, "method not allowed")
            return 200, {"agents": [self._agent_record()]}
        if len(parts) < 3 or parts[:2] != ["v1", "agents"] or parts[2] != self.agent.agent_id:
            raise HttpError(404, "not found")
        if len(parts) == 3:
            if method != "GET":
                raise HttpError(405, "method not allowed")
            return 200, self._agent_record()
        if parts[3:] == ["messages"]:
            if method != "POST":
                raise HttpError(405, "method not allowed")
            return self._send_message(self._json_object(body))
        if parts[3:] == ["pending"]:
            if method != "GET":
                raise HttpError(405, "method not allowed")
            return 200, {"deliveries": [self._public_delivery(item) for item in self.mailbox.pending()]}
        if len(parts) == 5 and parts[3] == "deliveries":
            delivery = self.mailbox.get(parts[4])
            if delivery is None or delivery["source"] != "automation":
                raise HttpError(404, "delivery not found")
            if method == "GET":
                return 200, self._public_delivery(delivery)
            if method == "PATCH":
                data = self._json_object(body)
                text = self._text(data)
                try:
                    return 200, self._public_delivery(self.mailbox.edit_queued(parts[4], self._prompt(text)))
                except DeliveryStateError as error:
                    raise HttpError(409, str(error)) from None
            raise HttpError(405, "method not allowed")
        if len(parts) == 6 and parts[3] == "deliveries" and parts[5] == "cancel":
            if method != "POST":
                raise HttpError(405, "method not allowed")
            delivery = self.mailbox.get(parts[4])
            if delivery is None or delivery["source"] != "automation":
                raise HttpError(404, "delivery not found")
            try:
                return 200, self._public_delivery(self.mailbox.cancel_queued(parts[4]))
            except DeliveryStateError as error:
                raise HttpError(409, str(error)) from None
        raise HttpError(404, "not found")

    def _send_message(self, data: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        text = self._text(data)
        conversation_id = data.get("conversation_id", "default")
        if not isinstance(conversation_id, str) or not CONVERSATION_ID.fullmatch(conversation_id):
            raise HttpError(400, "invalid conversation_id")
        idempotency_key = data.get("idempotency_key", uuid4().hex)
        if (
            not isinstance(idempotency_key, str)
            or not idempotency_key
            or len(idempotency_key) > 200
            or not idempotency_key.isprintable()
        ):
            raise HttpError(400, "invalid idempotency_key")
        try:
            delivery, created = self.mailbox.enqueue(
                source="automation",
                idempotency_key=f"automation:{idempotency_key}",
                session_key=f"automation:{conversation_id}",
                prompt=self._prompt(text),
                automation_rate_limit=self.settings.runs_per_hour,
            )
        except AutomationRateLimit as error:
            raise HttpError(
                429, str(error), {"Retry-After": str(error.retry_after)}
            ) from None
        except IdempotencyConflict as error:
            raise HttpError(409, str(error)) from None
        if created:
            self.on_enqueue()
        result = self._public_delivery(delivery)
        result["created"] = created
        return (202 if created else 200), result

    @staticmethod
    def _json_object(body: bytes) -> dict[str, Any]:
        try:
            value = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise HttpError(400, "a JSON object is required") from None
        if not isinstance(value, dict):
            raise HttpError(400, "a JSON object is required")
        return value

    @staticmethod
    def _text(data: dict[str, Any]) -> str:
        text = data.get("text")
        if not isinstance(text, str) or not text.strip():
            raise HttpError(400, "text must be a non-empty string")
        return text

    def _prompt(self, text: str) -> str:
        return f"""You are {self.agent.display_name} ({self.agent.agent_id}) in Mo's private Army Hub.
This request came through the owner-authenticated local automation API.
Never impersonate another agent or claim unperformed work.
GitHub is the code source of truth; submit branches and pull requests rather than treating chat as code storage.
Do not merge, deploy, spend money, delete repositories, force-push, or handle credentials without Mo's explicit approval.

Request:
{text}"""

    def _agent_record(self) -> dict[str, Any]:
        return {
            "id": self.agent.agent_id,
            "display_name": self.agent.display_name,
            "api_version": 1,
            "capabilities": ["messages", "delivery_status", "queued_edit", "queued_cancel"],
        }

    @staticmethod
    def _public_delivery(delivery: dict[str, Any]) -> dict[str, Any]:
        names = (
            "id",
            "status",
            "source",
            "session_key",
            "response",
            "error",
            "created_at",
            "updated_at",
            "ended_at",
        )
        return {name: delivery.get(name) for name in names}

    @staticmethod
    async def _send_json(
        writer: asyncio.StreamWriter,
        status: int,
        payload: dict[str, Any],
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode()
        headers = {
            "Content-Type": "application/json",
            "Content-Length": str(len(body)),
            "Cache-Control": "no-store",
            "Connection": "close",
            "X-Content-Type-Options": "nosniff",
            **(extra_headers or {}),
        }
        reason = {200: "OK", 202: "Accepted"}.get(status, "Error")
        writer.write(f"HTTP/1.1 {status} {reason}\r\n".encode())
        for name, value in headers.items():
            writer.write(f"{name}: {value}\r\n".encode())
        writer.write(b"\r\n" + body)
        try:
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()
