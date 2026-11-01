from __future__ import annotations

import json
import os
from pathlib import Path
import threading
from typing import Any

import yaml


class ManagerStore:
    """Small atomic metadata store. Secrets and Matrix tokens never belong here."""

    def __init__(self, root: Path):
        self.root = root
        self.runtime = root / ".runtime"
        self.directory = self.runtime / "agent-manager"
        self.path = self.directory / "state.json"
        self.lock = threading.RLock()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.state = self._load()

    def _load(self) -> dict[str, Any]:
        directory = yaml.safe_load((self.root / "agents" / "directory.yaml").read_text(encoding="utf-8"))
        rooms = json.loads((self.runtime / "rooms.json").read_text(encoding="utf-8"))
        all_rooms = [record["room_id"] for record in rooms.values()]
        if self.path.exists():
            state = json.loads(self.path.read_text(encoding="utf-8"))
            directory_records = {record["id"]: record for record in directory["agents"]}
            for agent_id, record in state.get("agents", {}).items():
                source = directory_records.get(agent_id, {})
                record.setdefault("display_name", source.get("display_name", agent_id))
                record.setdefault("mxid", source.get("mxid", f"@{agent_id}:army.local"))
                record.setdefault("provider", {"hermes": "auto", "dsh": "deepseek-official"}.get(record.get("harness")))
                record.setdefault("rooms", all_rooms if record.get("status") == "active" else [])
            state.setdefault("credentials", {})
            state.setdefault("audit", [])
            return state
        agents = {}
        for record in directory["agents"]:
            agents[record["id"]] = {
                "id": record["id"],
                "mxid": record["mxid"],
                "display_name": record["display_name"],
                "machine": record["machine"],
                "harness": record["harness"],
                "status": record["status"],
                "model": "deepseek-v4-pro" if record["status"] == "active" else None,
                "provider": {"hermes": "auto", "dsh": "deepseek-official"}.get(record["harness"]),
                "effort": None,
                "project": "mac-server" if record["status"] == "active" else None,
                "rooms": all_rooms if record["status"] == "active" else [],
                "managed": False,
            }
        state = {"version": 1, "agents": agents, "credentials": {}, "audit": []}
        self._write(state)
        return state

    def _write(self, state: dict[str, Any]) -> None:
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.chmod(temporary, 0o600)
        temporary.replace(self.path)

    def save(self) -> None:
        with self.lock:
            self._write(self.state)

    def agents(self) -> list[dict[str, Any]]:
        with self.lock:
            return [dict(record) for record in self.state["agents"].values()]

    def agent(self, agent_id: str) -> dict[str, Any]:
        with self.lock:
            try:
                return dict(self.state["agents"][agent_id])
            except KeyError as error:
                raise LookupError("Agent not found") from error

    def put_agent(self, record: dict[str, Any]) -> None:
        with self.lock:
            self.state["agents"][record["id"]] = dict(record)
            self.save()

    def credentials(self, agent_id: str) -> list[dict[str, Any]]:
        with self.lock:
            return [dict(record) for record in self.state["credentials"].get(agent_id, [])]

    def put_credential(self, agent_id: str, record: dict[str, Any]) -> None:
        with self.lock:
            records = self.state["credentials"].setdefault(agent_id, [])
            records[:] = [item for item in records if item["id"] != record["id"]]
            records.append(dict(record))
            self.save()

    def delete_credential(self, agent_id: str, credential_id: str) -> dict[str, Any]:
        with self.lock:
            records = self.state["credentials"].get(agent_id, [])
            for record in records:
                if record["id"] == credential_id:
                    records.remove(record)
                    self.save()
                    return dict(record)
        raise LookupError("Credential not found")

    def audit(self, actor: str, agent_id: str, action: str, result: str) -> None:
        from datetime import datetime, timezone
        with self.lock:
            self.state["audit"].append({
                "at": datetime.now(timezone.utc).isoformat(),
                "actor": actor,
                "agent_id": agent_id,
                "action": action,
                "result": result,
            })
            self.state["audit"] = self.state["audit"][-500:]
            self.save()
