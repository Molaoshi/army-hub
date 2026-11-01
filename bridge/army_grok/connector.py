from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
import re
import secrets
import time
from typing import Any
import urllib.request

from nio import AsyncClient, RoomMessageText, SyncError

from army_bridge.policy import admission_denial, delegation_fingerprint, thread_root

from .config import Settings
from .mcp import MCPServer
from .security import signed_webhook_headers

LOG = logging.getLogger(__name__)
PROTOCOL_KEY = "com.molaoshi.army_hub"


def _bounded_turn_delay(last_turn_at: float, interval: float, now: float) -> float:
    elapsed = now - float(last_turn_at)
    return min(interval, max(0.0, interval - elapsed))


class ConnectorState:
    def __init__(self, path: Path):
        self.path = path
        self.data: dict[str, Any] = {
            "next_batch": None,
            "processed_event_ids": [],
            "delegation_fingerprints": [],
            "last_turn_at": 0.0,
            "pending_replies": {},
        }
        if path.exists():
            self.data.update(json.loads(path.read_text(encoding="utf-8")))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data["processed_event_ids"] = self.data["processed_event_ids"][-5000:]
        self.data["delegation_fingerprints"] = self.data["delegation_fingerprints"][-1000:]
        now = time.time()
        self.data["pending_replies"] = {
            token: record for token, record in self.data["pending_replies"].items()
            if float(record.get("expires_at", 0)) > now and not record.get("used")
        }
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.data, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)
        self.path.chmod(0o600)


class GrokConnector:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.state = ConnectorState(settings.state_path)
        self.client = AsyncClient(
            settings.matrix.homeserver,
            settings.matrix.user_id,
            device_id=settings.matrix.device_id or "ARMYGROK",
        )
        self.client.access_token = settings.matrix.access_token
        self.mcp = MCPServer(settings.host, settings.port, settings.grok.mcp_path_secret)
        self.stop_event = asyncio.Event()
        self.inflight_tokens: set[str] = set()

    async def run(self) -> None:
        self.mcp.start(self.reply_from_grok, asyncio.get_running_loop())
        LOG.info("Grok MCP server listening on loopback port %s", self.settings.port)
        first_sync = not self.state.data.get("next_batch")
        backoff = 1
        try:
            while not self.stop_event.is_set():
                try:
                    response = await self.client.sync(
                        timeout=30_000,
                        since=self.state.data.get("next_batch"),
                        full_state=False,
                    )
                    if isinstance(response, SyncError):
                        raise RuntimeError(f"Matrix sync failed: {response}")
                    if not first_sync:
                        await self._process_sync(response)
                    self.state.data["next_batch"] = response.next_batch
                    self.state.save()
                    first_sync = False
                    backoff = 1
                except asyncio.CancelledError:
                    break
                except Exception:
                    LOG.exception("Matrix loop failed; retrying in %s seconds", backoff)
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 60)
        finally:
            self.mcp.stop()
            await self.client.close()

    async def _process_sync(self, response: Any) -> None:
        for room_id, room in response.rooms.join.items():
            if room_id not in self.settings.matrix.allowed_rooms:
                continue
            for event in room.timeline.events:
                if isinstance(event, RoomMessageText):
                    await self._process_message(room_id, event)

    async def _process_message(self, room_id: str, event: RoomMessageText) -> None:
        event_id = event.event_id
        if event_id in self.state.data["processed_event_ids"]:
            return
        self.state.data["processed_event_ids"].append(event_id)
        content = dict(event.source.get("content", {}))
        denial = admission_denial(
            content=content,
            sender=event.sender,
            room_id=room_id,
            user_id=self.settings.matrix.user_id,
            agent_id="grok",
            allowed_users=self.settings.matrix.allowed_users,
            allowed_rooms=self.settings.matrix.allowed_rooms,
            allow_agent_senders=self.settings.policy.allow_agent_senders,
        )
        if denial:
            LOG.info("Ignored %s from %s: %s", event_id, event.sender, denial)
            self.state.save()
            return

        body = content.get("body", "")
        root = thread_root(content, event_id)
        if len(body) > self.settings.policy.max_message_chars:
            await self._send(room_id, root, event_id, "@mo message exceeds the configured size limit.", 0, "m.notice")
            return
        fingerprint = delegation_fingerprint(event.sender, root, body)
        if fingerprint in self.state.data["delegation_fingerprints"]:
            LOG.warning("Suppressed repeated delegation %s in %s", event_id, root)
            self.state.save()
            return
        self.state.data["delegation_fingerprints"].append(fingerprint)
        incoming_turn = 0 if event.sender == "@mo:army.local" else int(content.get(PROTOCOL_KEY, {}).get("agent_turn", 1))
        if incoming_turn >= self.settings.policy.max_agent_turns:
            await self._send(room_id, root, event_id, "@mo agent turn budget exhausted; further collaboration needs your explicit continuation.", 0, "m.notice")
            return

        delay = _bounded_turn_delay(
            self.state.data.get("last_turn_at", 0),
            self.settings.policy.min_turn_interval_seconds,
            time.time(),
        )
        if delay:
            await asyncio.sleep(delay)

        token = secrets.token_urlsafe(32)
        self.state.data["pending_replies"][token] = {
            "room_id": room_id,
            "thread_root": root,
            "reply_to": event_id,
            "agent_turn": incoming_turn + 1,
            "expires_at": time.time() + self.settings.grok.reply_token_ttl_seconds,
            "used": False,
        }
        self.state.data["last_turn_at"] = time.time()
        self.state.save()
        payload = {
            "event": "matrix.message",
            "event_id": event_id,
            "room_id": room_id,
            "thread_root": root,
            "sender": event.sender,
            "text": body,
            "reply_token": token,
            "reply_tool": "army_reply",
        }
        try:
            delivery_id = await asyncio.to_thread(self._trigger_grok, payload)
            self.state.data["pending_replies"][token]["delivery_id"] = delivery_id
            self.state.save()
            LOG.info("Grok accepted Matrix event %s", event_id)
        except Exception as error:
            self.state.data["pending_replies"].pop(token, None)
            self.state.save()
            LOG.exception("Grok delivery failed for %s", event_id)
            await self._send(room_id, root, event_id, f"@mo Grok could not accept the turn: {self._safe_error(error)}", 0, "m.notice")

    def _trigger_grok(self, payload: dict[str, Any]) -> str:
        body = json.dumps(payload, separators=(",", ":")).encode()
        headers = signed_webhook_headers(body, self.settings.grok.signing_secret)
        request = urllib.request.Request(
            self.settings.grok.webhook_url,
            data=body,
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.settings.policy.request_timeout_seconds) as response:
            if response.status != 202:
                raise RuntimeError(f"unexpected Grok HTTP status {response.status}")
        return headers["webhook-id"]

    async def reply_from_grok(self, token: str, text: str) -> dict[str, Any]:
        if token in self.inflight_tokens:
            raise RuntimeError("reply_already_in_progress")
        record = self.state.data["pending_replies"].get(token)
        if not record or record.get("used"):
            raise RuntimeError("reply_token_invalid_or_used")
        if float(record["expires_at"]) <= time.time():
            self.state.data["pending_replies"].pop(token, None)
            self.state.save()
            raise RuntimeError("reply_token_expired")
        self.inflight_tokens.add(token)
        try:
            event_id = await self._send(
                record["room_id"], record["thread_root"], record["reply_to"],
                text, int(record["agent_turn"]), "m.text",
            )
            record["used"] = True
            record["matrix_event_id"] = event_id
            self.state.data["pending_replies"].pop(token, None)
            self.state.save()
            return {"event_id": event_id, "thread_root": record["thread_root"]}
        finally:
            self.inflight_tokens.discard(token)

    async def _send(self, room_id: str, root: str, reply_to: str, body: str, agent_turn: int, msgtype: str) -> str:
        mentioned = []
        for user_id in self.settings.matrix.allowed_users:
            localpart = user_id[1:].split(":", 1)[0]
            if re.search(rf"(?<![\w.@-])@{re.escape(localpart)}(?![\w.:-])", body, re.IGNORECASE):
                mentioned.append(user_id)
        content = {
            "msgtype": msgtype,
            "body": body,
            "m.mentions": {"user_ids": mentioned},
            PROTOCOL_KEY: {"agent_turn": agent_turn, "agent_id": "grok"},
            "m.relates_to": {
                "rel_type": "m.thread",
                "event_id": root,
                "is_falling_back": True,
                "m.in_reply_to": {"event_id": reply_to},
            },
        }
        response = await self.client.room_send(room_id, "m.room.message", content)
        if getattr(response, "event_id", None) is None:
            raise RuntimeError(f"Matrix send failed: {response}")
        return response.event_id

    @staticmethod
    def _safe_error(error: Exception) -> str:
        text = str(error).replace("\n", " ")
        return text[:300] if text else error.__class__.__name__
