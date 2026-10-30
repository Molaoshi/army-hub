from __future__ import annotations

import hashlib
import re
from typing import Any


def thread_root(content: dict[str, Any], event_id: str) -> str:
    relation = content.get("m.relates_to", {})
    if relation.get("rel_type") == "m.thread" and isinstance(relation.get("event_id"), str):
        return relation["event_id"]
    return event_id


def explicitly_mentioned(content: dict[str, Any], user_id: str, agent_id: str) -> bool:
    mentions = content.get("m.mentions", {})
    mentioned_users = mentions.get("user_ids", [])
    if user_id in mentioned_users:
        return True

    formatted = content.get("formatted_body", "")
    if f"https://matrix.to/#/{user_id}" in formatted:
        return True

    body = content.get("body", "")
    if re.search(r"(?<![\w.@-])@room(?![\w.-])", body, re.IGNORECASE):
        return False
    pattern = rf"(?<![\w.@-])@{re.escape(agent_id)}(?::{re.escape(user_id.split(':', 1)[1])})?(?![\w.-])"
    return re.search(pattern, body, re.IGNORECASE) is not None


def admission_denial(
    *,
    content: dict[str, Any],
    sender: str,
    room_id: str,
    user_id: str,
    agent_id: str,
    allowed_users: set[str],
    allowed_rooms: set[str],
    allow_agent_senders: bool,
) -> str | None:
    if sender == user_id:
        return "own_event"
    if room_id not in allowed_rooms:
        return "room_not_allowed"
    if sender not in allowed_users:
        return "sender_not_allowed"
    if not allow_agent_senders and sender != "@mo:army.local":
        return "agent_sender_not_allowed"
    if content.get("msgtype") != "m.text":
        return "not_plain_text"
    if not explicitly_mentioned(content, user_id, agent_id):
        return "not_explicitly_mentioned"
    return None


def delegation_fingerprint(sender: str, root: str, body: str) -> str:
    normalized = " ".join(body.lower().split())
    return hashlib.sha256(f"{sender}\0{root}\0{normalized}".encode()).hexdigest()
