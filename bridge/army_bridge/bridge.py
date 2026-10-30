from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
import re
import time
from typing import Any

from nio import AsyncClient, RoomMessageText, SyncError

from .acp import SessionManager
from .config import Settings
from .policy import admission_denial, delegation_fingerprint, thread_root

LOG = logging.getLogger(__name__)
PROTOCOL_KEY = "com.molaoshi.army_hub"


class BridgeState:
    def __init__(self, path: Path):
        self.path = path
        self.data: dict[str, Any] = {
            "next_batch": None,
            "processed_event_ids": [],
            "sessions": {},
            "delegation_fingerprints": [],
            "last_turn_at": 0.0,
        }
        if path.exists():
            self.data.update(json.loads(path.read_text(encoding="utf-8")))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data["processed_event_ids"] = self.data["processed_event_ids"][-5000:]
        self.data["delegation_fingerprints"] = self.data["delegation_fingerprints"][-1000:]
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.data, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)
        self.path.chmod(0o600)


class ArmyBridge:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.state = BridgeState(settings.state_path)
        self.client = AsyncClient(
            settings.matrix.homeserver,
            settings.matrix.user_id,
            device_id=settings.matrix.device_id or "ARMYHUB",
        )
        self.client.access_token = settings.matrix.access_token
        self.sessions = SessionManager(settings.agent, settings.policy.prompt_timeout_seconds)
        self.stop_event = asyncio.Event()

    @property
    def agent_id(self) -> str:
        return self.settings.agent.agent_id

    @property
    def user_id(self) -> str:
        return self.settings.matrix.user_id

    async def run(self) -> None:
        first_sync = not self.state.data.get("next_batch")
        backoff = 1
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
        await self.close()

    async def close(self) -> None:
        await self.sessions.client.close()
        await self.client.close()

    def stop(self) -> None:
        self.stop_event.set()

    async def _process_sync(self, response: Any) -> None:
        for room_id, room in response.rooms.join.items():
            if room_id not in self.settings.matrix.allowed_rooms:
                continue
            for event in room.timeline.events:
                if not isinstance(event, RoomMessageText):
                    continue
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
            user_id=self.user_id,
            agent_id=self.agent_id,
            allowed_users=self.settings.matrix.allowed_users,
            allowed_rooms=self.settings.matrix.allowed_rooms,
            allow_agent_senders=self.settings.policy.allow_agent_senders,
        )
        if denial:
            LOG.info("Ignored %s from %s: %s", event_id, event.sender, denial)
            self.state.save()
            return

        body = content.get("body", "")
        if len(body) > self.settings.policy.max_message_chars:
            await self._notice(room_id, event_id, event_id, f"@{self._localpart(event.sender)} message exceeds the configured size limit.")
            return

        root = thread_root(content, event_id)
        fingerprint = delegation_fingerprint(event.sender, root, body)
        if fingerprint in self.state.data["delegation_fingerprints"]:
            LOG.warning("Suppressed repeated delegation %s in %s", event_id, root)
            self.state.save()
            return
        self.state.data["delegation_fingerprints"].append(fingerprint)

        incoming_turn = 0 if event.sender == "@mo:army.local" else int(content.get(PROTOCOL_KEY, {}).get("agent_turn", 1))
        if incoming_turn >= self.settings.policy.max_agent_turns:
            await self._notice(
                room_id, root, event_id,
                "@mo agent turn budget exhausted; further collaboration needs your explicit continuation.",
            )
            return

        elapsed = time.monotonic() - float(self.state.data.get("last_turn_at", 0))
        if elapsed < self.settings.policy.min_turn_interval_seconds:
            await asyncio.sleep(self.settings.policy.min_turn_interval_seconds - elapsed)

        prompt = self._prompt(event.sender, room_id, root, body)
        try:
            session_key = root
            saved_session = self.state.data["sessions"].get(session_key)
            session_id, answer = await self.sessions.prompt(session_key, prompt, saved_session)
            self.state.data["sessions"][session_key] = session_id
            self.state.data["last_turn_at"] = time.monotonic()
            self.state.save()
            await self._send(room_id, root, event_id, answer, incoming_turn + 1, msgtype="m.text")
        except Exception as error:
            LOG.exception("Agent turn failed for %s", event_id)
            await self._notice(room_id, root, event_id, f"@mo {self.settings.agent.display_name} could not complete the turn: {self._safe_error(error)}")

    def _prompt(self, sender: str, room_id: str, root: str, body: str) -> str:
        return f"""You are {self.settings.agent.display_name} ({self.user_id}) in Mo's private Army Hub.

Protocol rules:
- You were explicitly mentioned; this is one authorized turn.
- Never impersonate another agent or claim unperformed work.
- Delegate only when useful by explicitly writing the target's Matrix localpart, such as @hermes-mini or @dsh-mini.
- A useful handoff includes Task, Repository, Scope, Required verification, and Expected result.
- GitHub is the code source of truth. Use the project registry and local clones; submit branches and pull requests rather than treating chat as code storage.
- Do not merge, deploy, spend money, delete repositories, force-push, or handle credentials without Mo's explicit approval.
- Keep your response concise and address @mo when human action is required.

Message metadata:
Sender: {sender}
Room: {room_id}
Thread root: {root}

Message:
{body}
"""

    async def _send(self, room_id: str, root: str, reply_to: str, body: str, agent_turn: int, msgtype: str) -> None:
        mentioned = []
        for user_id in self.settings.matrix.allowed_users:
            localpart = self._localpart(user_id)
            if re.search(rf"(?<![\w.@-])@{re.escape(localpart)}(?![\w.:-])", body, re.IGNORECASE):
                mentioned.append(user_id)
        content = {
            "msgtype": msgtype,
            "body": body,
            "m.mentions": {"user_ids": mentioned},
            PROTOCOL_KEY: {"agent_turn": agent_turn, "agent_id": self.agent_id},
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

    async def _notice(self, room_id: str, root: str, reply_to: str, body: str) -> None:
        await self._send(room_id, root, reply_to, body, 0, msgtype="m.notice")

    @staticmethod
    def _localpart(user_id: str) -> str:
        return user_id[1:].split(":", 1)[0]

    @staticmethod
    def _safe_error(error: Exception) -> str:
        text = str(error).replace("\n", " ")
        return text[:300] if text else error.__class__.__name__
