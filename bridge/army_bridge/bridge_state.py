from __future__ import annotations

import json
from pathlib import Path
from typing import Any


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
