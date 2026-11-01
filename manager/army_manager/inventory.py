from __future__ import annotations

import json
from pathlib import Path
import subprocess
from typing import Any

import yaml


class Inventory:
    def __init__(self, root: Path):
        self.root = root
        self.workspace = root.parent

    def machines(self) -> list[dict[str, Any]]:
        return [
            {"id": "mini", "name": "Mac mini", "status": "online", "enrolled": True},
            {"id": "dell", "name": "Dell", "status": "unenrolled", "enrolled": False},
            {"id": "book", "name": "MacBook", "status": "unenrolled", "enrolled": False},
        ]

    def harnesses(self, machine: str) -> list[dict[str, Any]]:
        if machine != "mini":
            return []
        records = []
        hermes = Path.home() / ".local" / "bin" / "hermes"
        dsh = self.workspace / ".runtime" / "dsh-acp.sh"
        if hermes.exists():
            records.append({"id": "hermes", "name": "Hermes", "version": self._version([str(hermes), "acp", "--version"])})
        if dsh.exists():
            records.append({"id": "dsh", "name": "DeepSeek Harness", "version": self._version([str(dsh), "--version"])})
        return records

    @staticmethod
    def _version(command: list[str]) -> str:
        try:
            return subprocess.check_output(command, text=True, timeout=15, stderr=subprocess.STDOUT).strip()
        except (OSError, subprocess.SubprocessError):
            return "detected"

    def models(self, machine: str, harness: str) -> list[dict[str, Any]]:
        if machine != "mini":
            return []
        if harness == "dsh":
            return [{"id": "default", "name": "Harness profile default", "provider": "deepseek", "efforts": []}]
        if harness != "hermes":
            return []
        catalog = self.workspace / ".runtime" / "dsh" / "node_modules" / "@earendil-works" / "pi-ai" / "dist" / "providers" / "data" / "deepseek.json"
        if not catalog.exists():
            return []
        raw = json.loads(catalog.read_text(encoding="utf-8"))
        models = []
        for group in raw.values():
            for record in group.values():
                if record.get("type") != "chat":
                    continue
                models.append({
                    "id": record["id"], "name": record["name"], "provider": record["provider"],
                    "input": record.get("input", ["text"]),
                    # ACP does not currently expose a verified per-agent effort setter.
                    "efforts": [],
                })
        return sorted(models, key=lambda item: item["name"])

    def projects(self, machine: str) -> list[dict[str, Any]]:
        raw = yaml.safe_load((self.root / "projects" / "registry.yaml").read_text(encoding="utf-8"))
        projects = []
        for project_id, record in raw["projects"].items():
            path = record.get("local_paths", {}).get(machine)
            if not path or not Path(path).is_dir():
                continue
            projects.append({"id": project_id, "name": project_id.replace("-", " ").title(),
                             "path": path, "repository": record.get("repository"),
                             "room_alias": record.get("matrix_room_alias")})
        return projects
