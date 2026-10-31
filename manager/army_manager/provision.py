from __future__ import annotations

import re
from typing import Any

from .connectors import ConnectorManager, ConnectorError
from .inventory import Inventory
from .matrix import MatrixClient, MatrixError
from .store import ManagerStore


class Provisioner:
    def __init__(self, store: ManagerStore, matrix: MatrixClient, inventory: Inventory, connectors: ConnectorManager):
        self.store = store
        self.matrix = matrix
        self.inventory = inventory
        self.connectors = connectors

    def _validate_runtime(self, payload: dict[str, Any]) -> dict[str, Any]:
        machine = payload.get("machine")
        harness = payload.get("harness")
        model = payload.get("model")
        project = payload.get("project")
        if harness not in {item["id"] for item in self.inventory.harnesses(machine)}:
            raise ValueError("Selected harness is unavailable on this machine")
        models = {item["id"]: item for item in self.inventory.models(machine, harness)}
        if model not in models:
            raise ValueError("Selected model is unavailable for this harness")
        if project not in {item["id"] for item in self.inventory.projects(machine)}:
            raise ValueError("Selected project is unavailable on this machine")
        available_rooms = {item["id"] for item in self.matrix.rooms()}
        rooms = list(dict.fromkeys(payload.get("rooms", [])))
        if not rooms or not set(rooms).issubset(available_rooms):
            raise ValueError("Select at least one valid Matrix room")
        effort = payload.get("effort")
        if effort and effort not in models[model]["efforts"]:
            raise ValueError("Selected effort is unsupported")
        return {"machine": machine, "harness": harness, "model": model,
                "effort": effort, "project": project, "rooms": rooms}

    def validate(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("display_name", "")).strip()
        if not 1 <= len(name) <= 80:
            raise ValueError("Display name must be between 1 and 80 characters")
        agent_id = re.sub(r"-+", "-", re.sub(r"[^a-z0-9-]", "-", name.lower()).strip("-")[:40])
        if not agent_id:
            raise ValueError("Display name does not produce a valid agent ID")
        existing = self.store.state["agents"].get(agent_id)
        if existing and existing.get("status") != "failed":
            raise ValueError(f"Agent ID {agent_id} already exists; choose a unique name")
        return {"id": agent_id, "mxid": f"@{agent_id}:army.local", "display_name": name,
                **self._validate_runtime(payload), "status": "active", "managed": True}

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        record = self.validate(payload)
        identity = self.matrix.credentials().get(record["id"])
        if not identity:
            identity = self.matrix.create_agent_identity(record["id"], record["display_name"])
        try:
            self.connectors.render_config(record, identity)
            self.matrix.sync_rooms(record["id"], record["rooms"])
            self.store.put_agent(record)
            self.connectors.start(record["id"])
        except Exception:
            record["status"] = "failed"
            self.store.put_agent(record)
            raise
        self.store.audit("@mo:army.local", record["id"], "agent.create", "ready")
        return record

    def update(self, agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        current = self.store.agent(agent_id)
        runtime = self._validate_runtime({**payload, "machine": current["machine"]})
        record = {**current, **runtime, "managed": True}
        identity = self.matrix.credentials()[agent_id]
        self.connectors.render_config(record, identity)
        self.matrix.sync_rooms(agent_id, record["rooms"], current.get("rooms", []))
        self.store.put_agent(record)
        if self.connectors.pid(agent_id):
            self.connectors.restart(agent_id)
        self.store.audit("@mo:army.local", agent_id, "agent.configure", "updated")
        return record
