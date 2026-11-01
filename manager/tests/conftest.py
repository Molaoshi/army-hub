from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile

import pytest
import yaml


def make_root(root: Path) -> Path:
    (root / "agents").mkdir(parents=True)
    (root / "projects").mkdir()
    (root / ".runtime").mkdir()
    (root / ".venv-service" / "bin").mkdir(parents=True)
    (root / "agents" / "directory.yaml").write_text(yaml.safe_dump({
        "agents": [
            {"id": "hermes-mini", "mxid": "@hermes-mini:army.local", "display_name": "Hermes Mini", "harness": "hermes", "machine": "mini", "status": "active"},
            {"id": "dsh-mini", "mxid": "@dsh-mini:army.local", "display_name": "DSH Mini", "harness": "dsh", "machine": "mini", "status": "active"},
        ]
    }))
    (root / "projects" / "registry.yaml").write_text(yaml.safe_dump({"projects": {
        "army-hub": {"repository": "repo", "local_paths": {"mini": str(root)}, "matrix_room_alias": "#army-lab:army.local"}
    }}))
    (root / ".runtime" / "rooms.json").write_text(json.dumps({"army-lab": {"room_id": "!lab:army.local", "alias": "#army-lab:army.local", "members": []}}))
    (root / ".runtime" / "credentials.json").write_text(json.dumps({
        "hermes-mini": {"mxid": "@hermes-mini:army.local", "access_token": "matrix-secret", "device_id": "one"},
        "dsh-mini": {"mxid": "@dsh-mini:army.local", "access_token": "other-secret", "device_id": "two"},
    }))
    return root


def pytest_sessionstart(session):
    # API imports construct their production dependencies; point them only at disposable fixtures.
    root = make_root(Path(tempfile.mkdtemp(prefix="army-manager-tests-")) / "army-hub")
    os.environ["ARMY_HUB_ROOT"] = str(root)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return make_root(tmp_path / "army-hub")
