from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
import re
import time
from typing import Any
import uuid

from nio import AsyncClient, RoomMessageText, SyncError

from army_bridge.policy import admission_denial, delegation_fingerprint, thread_root

from .config import Settings
from .gateway import GatewayClient

LOG = logging.getLogger(__name__)
PROTOCOL_KEY = "com.molaoshi.army_hub"


class ConnectorState:
    def __init__(self, path: Path):
        self.path = path
        self.data: dict[str, Any] = {
            "next_batch": None,
            "processed_event_ids": [],
            "delegation_fingerprints": [],
            "last_turn_at": 0.0,
            "pending_turns": {},
            "completed_turns": [],
        }
        if path.exists():
            self.data.update(json.loads(path.read_text(encoding="utf-8")))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data["processed_event_ids"] = self.data["processed_event_ids"][-5000:]
        self.data["delegation_fingerprints"] = self.data["delegation_fingerprints"][-1000:]
        self.data["completed_turns"] = self.data["completed_turns"][-200:]
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.data, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)
        self.path.chmod(0o600)


class GrokGatewayConnector:
    def __init__(self, settings: Settings, gateway: GatewayClient | None = None):
        self.settings = settings
        self.state = ConnectorState(settings.state_path)
        self.client = AsyncClient(
            settings.matrix.homeserver,
            settings.matrix.user_id,
            device_id=settings.matrix.device_id or "ARMYGROKGW",
        )
        self.client.access_token = settings.matrix.access_token
        self.gateway = gateway or GatewayClient(settings.gateway)
        self.stop_event = asyncio.Event()

    async def run(self) -> None:
        health = await asyncio.to_thread(self.gateway.health)
        if health.get("ok") is not True:
            raise RuntimeError("Grok gateway is not healthy")
        LOG.info("Connected to native Grok gateway for one persistent agent")
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
                    if first_sync:
                        await self.recover_pending()
                    first_sync = False
                    backoff = 1
                except asyncio.CancelledError:
                    break
                except Exception:
                    LOG.exception("Matrix loop failed; retrying in %s seconds", backoff)
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 60)
        finally:
            await self.client.close()

    async def recover_pending(self) -> None:
        for nonce in list(self.state.data["pending_turns"]):
            record = self.state.data["pending_turns"].get(nonce)
            if record and record.get("status") != "completed":
                LOG.info("Recovering persisted Grok turn %s", nonce)
                await self._deliver(nonce)

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
            await self._send(room_id, root, event_id, "@mo message exceeds the configured size limit.", 0, "m.notice", uuid.uuid4().hex)
            return
        fingerprint = delegation_fingerprint(event.sender, root, body)
        if fingerprint in self.state.data["delegation_fingerprints"]:
            LOG.warning("Suppressed repeated delegation %s in %s", event_id, root)
            self.state.save()
            return
        self.state.data["delegation_fingerprints"].append(fingerprint)
        incoming_turn = 0 if event.sender == "@mo:army.local" else int(content.get(PROTOCOL_KEY, {}).get("agent_turn", 1))
        if incoming_turn >= self.settings.policy.max_agent_turns:
            await self._send(room_id, root, event_id, "@mo agent turn budget exhausted; further collaboration needs your explicit continuation.", 0, "m.notice", uuid.uuid4().hex)
            return

        elapsed = time.time() - float(self.state.data.get("last_turn_at", 0))
        if elapsed < self.settings.policy.min_turn_interval_seconds:
            await asyncio.sleep(self.settings.policy.min_turn_interval_seconds - elapsed)

        nonce = uuid.uuid4().hex
        self.state.data["pending_turns"][nonce] = {
            "status": "created",
            "room_id": room_id,
            "thread_root": root,
            "reply_to": event_id,
            "agent_turn": incoming_turn + 1,
            "sender": event.sender,
            "text": body,
            "created_at": time.time(),
        }
        self.state.data["last_turn_at"] = time.time()
        self.state.save()
        await self._deliver(nonce)

    async def _deliver(self, nonce: str) -> None:
        record = self.state.data["pending_turns"].get(nonce)
        if not record or record.get("status") == "completed":
            return
        try:
            if record["status"] in {"created", "failed"}:
                observed = await asyncio.to_thread(self.gateway.prompt_observed, nonce)
                if not observed:
                    prompt = (
                        f"Matrix message from {record['sender']} (event {record['reply_to']}):\n"
                        f"{record['text']}\n\n"
                        "Reply to this Matrix message. Keep this same Army Hub Bot conversation."
                    )
                    await asyncio.to_thread(self.gateway.send_prompt, prompt, nonce)
                record["status"] = "accepted"
                record.pop("error", None)
                self.state.save()
            reply = await asyncio.to_thread(self.gateway.wait_for_reply, nonce)
            event_id = await self._send(
                record["room_id"], record["thread_root"], record["reply_to"],
                reply.text, int(record["agent_turn"]), "m.text", nonce,
            )
            record["status"] = "completed"
            record["matrix_event_id"] = event_id
            record["grok_entry_ids"] = list(reply.entry_ids)
            record["request_id"] = reply.prompt_request_id
            record["shared_request_id"] = reply.shared_request_id
            self.state.data["completed_turns"].append({"nonce": nonce, **record})
            self.state.data["pending_turns"].pop(nonce, None)
            self.state.save()
            LOG.info("Delivered native Grok reply for Matrix event %s", record["reply_to"])
        except Exception as error:
            if record.get("status") != "accepted":
                record["status"] = "failed"
            record["error"] = self._safe_error(error)
            self.state.save()
            LOG.exception("Native Grok delivery failed for %s", record["reply_to"])
            await self._send(
                record["room_id"], record["thread_root"], record["reply_to"],
                f"@mo Grok could not complete the turn: {self._safe_error(error)}",
                0, "m.notice", f"{nonce}-notice",
            )

    async def _send(self, room_id: str, root: str, reply_to: str, body: str, agent_turn: int, msgtype: str, nonce: str) -> str:
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
        response = await self.client.room_send(
            room_id, "m.room.message", content, tx_id=f"army-grok-gateway-{nonce}",
        )
        if getattr(response, "event_id", None) is None:
            raise RuntimeError(f"Matrix send failed: {response}")
        return response.event_id

    @staticmethod
    def _safe_error(error: Exception) -> str:
        text = str(error).replace("\n", " ")
        return text[:300] if text else error.__class__.__name__
