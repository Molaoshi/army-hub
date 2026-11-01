from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class MatrixSettings:
    homeserver: str
    user_id: str
    access_token: str
    device_id: str | None
    allowed_users: set[str]
    allowed_rooms: set[str]


@dataclass(frozen=True)
class GrokSettings:
    webhook_url: str
    signing_secret: str
    mcp_path_secret: str
    reply_token_ttl_seconds: int = 1800


@dataclass(frozen=True)
class PolicySettings:
    max_agent_turns: int = 6
    min_turn_interval_seconds: float = 2.0
    request_timeout_seconds: float = 30.0
    allow_agent_senders: bool = True
    max_message_chars: int = 40_000


@dataclass(frozen=True)
class Settings:
    matrix: MatrixSettings
    grok: GrokSettings
    policy: PolicySettings
    state_path: Path
    host: str = "127.0.0.1"
    port: int = 3105


def load_settings(path: str | Path) -> Settings:
    config_path = Path(path).resolve()
    raw: dict[str, Any] = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    matrix = raw["matrix"]
    grok = raw["grok"]
    state_path = Path(raw.get("state_path", config_path.parent / "grok-state.json"))
    if not state_path.is_absolute():
        state_path = config_path.parent / state_path
    return Settings(
        matrix=MatrixSettings(
            homeserver=matrix["homeserver"].rstrip("/"),
            user_id=matrix["user_id"],
            access_token=matrix["access_token"],
            device_id=matrix.get("device_id"),
            allowed_users=set(matrix.get("allowed_users", [])),
            allowed_rooms=set(matrix.get("allowed_rooms", [])),
        ),
        grok=GrokSettings(**grok),
        policy=PolicySettings(**raw.get("policy", {})),
        state_path=state_path,
        host=raw.get("host", "127.0.0.1"),
        port=int(raw.get("port", 3105)),
    )
