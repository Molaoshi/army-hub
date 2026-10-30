from __future__ import annotations

from dataclasses import dataclass, field
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
class AgentSettings:
    agent_id: str
    display_name: str
    command: list[str]
    cwd: str
    environment: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class PolicySettings:
    max_agent_turns: int = 6
    min_turn_interval_seconds: float = 2.0
    prompt_timeout_seconds: float = 600.0
    allow_agent_senders: bool = True
    max_message_chars: int = 40_000


@dataclass(frozen=True)
class Settings:
    matrix: MatrixSettings
    agent: AgentSettings
    policy: PolicySettings
    state_path: Path


def load_settings(path: str | Path) -> Settings:
    config_path = Path(path).resolve()
    raw: dict[str, Any] = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    matrix = raw["matrix"]
    agent = raw["agent"]
    policy = raw.get("policy", {})
    state_path = Path(raw.get("state_path", config_path.parent / "bridge-state.json"))
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
        agent=AgentSettings(
            agent_id=agent["id"],
            display_name=agent["display_name"],
            command=[str(part) for part in agent["command"]],
            cwd=agent["cwd"],
            environment={str(k): str(v) for k, v in agent.get("environment", {}).items()},
        ),
        policy=PolicySettings(**policy),
        state_path=state_path,
    )
