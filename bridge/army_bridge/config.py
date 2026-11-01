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
    session_config: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class PolicySettings:
    max_agent_turns: int = 6
    min_turn_interval_seconds: float = 2.0
    prompt_timeout_seconds: float = 600.0
    allow_agent_senders: bool = True
    max_message_chars: int = 40_000


@dataclass(frozen=True)
class AutomationSettings:
    enabled: bool = False
    body_limit_bytes: int = 32_768
    runs_per_hour: int = 30
    state_dir: Path | None = None


@dataclass(frozen=True)
class Settings:
    matrix: MatrixSettings
    agent: AgentSettings
    policy: PolicySettings
    state_path: Path
    mailbox_path: Path | None = None
    automation: AutomationSettings = field(default_factory=AutomationSettings)


def load_settings(path: str | Path) -> Settings:
    config_path = Path(path).resolve()
    raw: dict[str, Any] = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    matrix = raw["matrix"]
    agent = raw["agent"]
    policy = raw.get("policy", {})
    automation = raw.get("automation", {})

    def resolved_path(value: Any, default: Path) -> Path:
        candidate = Path(value) if value is not None else default
        return candidate if candidate.is_absolute() else config_path.parent / candidate

    state_path = resolved_path(raw.get("state_path"), config_path.parent / "bridge-state.json")
    mailbox_path = resolved_path(raw.get("mailbox_path"), state_path.with_suffix(".mailbox.sqlite3"))
    automation_dir = resolved_path(
        automation.get("state_dir"), state_path.parent / "automation" / agent["id"]
    )
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
            session_config={str(k): str(v) for k, v in agent.get("session_config", {}).items() if v},
        ),
        policy=PolicySettings(**policy),
        state_path=state_path,
        mailbox_path=mailbox_path,
        automation=AutomationSettings(
            enabled=bool(automation.get("enabled", False)),
            body_limit_bytes=int(automation.get("body_limit_bytes", 32_768)),
            runs_per_hour=int(automation.get("runs_per_hour", 30)),
            state_dir=automation_dir,
        ),
    )
