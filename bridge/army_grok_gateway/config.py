from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from army_grok.config import MatrixSettings, PolicySettings


@dataclass(frozen=True)
class GatewaySettings:
    base_url: str
    agent_id: str
    discovery_path: Path
    reply_timeout_seconds: float = 600.0
    poll_interval_seconds: float = 1.0
    stable_reply_seconds: float = 5.0


@dataclass(frozen=True)
class Settings:
    matrix: MatrixSettings
    gateway: GatewaySettings
    policy: PolicySettings
    state_path: Path


def _safe_url(value: str, name: str) -> str:
    url = value.rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme == "https":
        return url
    if parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}:
        return url
    raise ValueError(f"{name} must use HTTPS, except on loopback")


def load_settings(path: str | Path) -> Settings:
    config_path = Path(path).resolve()
    raw: dict[str, Any] = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    matrix = raw["matrix"]
    gateway = raw["gateway"]
    discovery_path = Path(gateway.get("discovery_path", "/home/box/sand-data/gateway.json"))
    if not discovery_path.is_absolute():
        discovery_path = config_path.parent / discovery_path
    state_path = Path(raw.get("state_path", config_path.parent / "grok-gateway-state.json"))
    if not state_path.is_absolute():
        state_path = config_path.parent / state_path
    return Settings(
        matrix=MatrixSettings(
            homeserver=_safe_url(matrix["homeserver"], "Matrix homeserver"),
            user_id=matrix["user_id"],
            access_token=matrix["access_token"],
            device_id=matrix.get("device_id"),
            allowed_users=set(matrix.get("allowed_users", [])),
            allowed_rooms=set(matrix.get("allowed_rooms", [])),
        ),
        gateway=GatewaySettings(
            base_url=_safe_url(gateway["base_url"], "Grok gateway"),
            agent_id=gateway["agent_id"],
            discovery_path=discovery_path,
            reply_timeout_seconds=float(gateway.get("reply_timeout_seconds", 600)),
            poll_interval_seconds=float(gateway.get("poll_interval_seconds", 1)),
            stable_reply_seconds=float(gateway.get("stable_reply_seconds", 5)),
        ),
        policy=PolicySettings(**raw.get("policy", {})),
        state_path=state_path,
    )
