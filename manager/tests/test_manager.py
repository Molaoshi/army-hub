from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

import pytest
import yaml

from army_manager.connectors import ConnectorManager
from army_manager.credentials import CredentialManager
from army_manager.inventory import Inventory
from army_manager.matrix import MatrixClient
from army_manager.provision import Provisioner
from army_manager.store import ManagerStore


def payload(**changes):
    value = {"display_name": "Researcher", "machine": "mini", "harness": "hermes",
             "model": "deepseek-v4-pro", "effort": None, "project": "army-hub", "rooms": ["!lab:army.local"]}
    value.update(changes)
    return value


def provisioner(root: Path):
    store = ManagerStore(root)
    matrix = Mock()
    matrix.rooms.return_value = [{"id": "!lab:army.local", "name": "Army Lab"}]
    matrix.credentials.return_value = json.loads((root / ".runtime" / "credentials.json").read_text())
    inventory = Mock()
    inventory.harnesses.side_effect = lambda machine: ([{"id": "hermes"}, {"id": "dsh"}] if machine == "mini" else [])
    inventory.models.side_effect = lambda machine, harness: ([{"id": "deepseek-v4-pro", "efforts": []}] if harness == "hermes" else [{"id": "default", "efforts": []}])
    inventory.projects.return_value = [{"id": "army-hub"}]
    return Provisioner(store, matrix, inventory, Mock()), store


def test_store_imports_existing_agents_without_matrix_secrets(root):
    store = ManagerStore(root)
    assert store.agent("hermes-mini")["display_name"] == "Hermes Mini"
    serialized = store.path.read_text()
    assert "matrix-secret" not in serialized
    assert "other-secret" not in serialized
    assert store.path.stat().st_mode & 0o777 == 0o600


def test_dependent_runtime_validation(root):
    manager, _ = provisioner(root)
    assert manager.validate(payload())["id"] == "researcher"
    with pytest.raises(ValueError, match="harness"):
        manager.validate(payload(machine="dell"))
    with pytest.raises(ValueError, match="model"):
        manager.validate(payload(model="invented-model"))
    with pytest.raises(ValueError, match="effort"):
        manager.validate(payload(effort="ultra"))
    with pytest.raises(ValueError, match="room"):
        manager.validate(payload(rooms=[]))


def test_duplicate_active_identity_rejected(root):
    manager, _ = provisioner(root)
    with pytest.raises(ValueError, match="already exists"):
        manager.validate(payload(display_name="Hermes Mini"))


def test_update_preserves_identity(root):
    manager, store = provisioner(root)
    record = manager.update("hermes-mini", payload(harness="dsh", model="default"))
    assert record["id"] == "hermes-mini"
    assert record["mxid"] == "@hermes-mini:army.local"
    assert record["harness"] == "dsh"


def test_rendered_config_uses_model_and_registered_workspace(root):
    store = ManagerStore(root)
    connectors = ConnectorManager(root, store)
    record = {"id": "researcher", "display_name": "Researcher", "harness": "hermes",
              "model": "deepseek-flash", "machine": "mini", "project": "army-hub", "rooms": ["!lab:army.local"]}
    matrix_record = {"mxid": "@researcher:army.local", "access_token": "private-matrix-token", "device_id": "device"}
    connectors.render_config(record, matrix_record)
    config = yaml.safe_load((root / ".runtime" / "researcher.yaml").read_text())
    assert config["agent"]["environment"]["HERMES_INFERENCE_MODEL"] == "deepseek-flash"
    assert config["agent"]["cwd"] == str(root)
    assert config["matrix"]["allowed_rooms"] == ["!lab:army.local"]
    assert (root / ".runtime" / "researcher.yaml").stat().st_mode & 0o777 == 0o600


def test_credentials_are_masked_and_scoped(root, monkeypatch):
    store = ManagerStore(root)
    manager = CredentialManager(store)
    secrets = {}

    def fake_run(arguments, secret=None):
        if arguments[0] == "add-generic-password":
            secrets[arguments[5]] = secret
            return ""
        if arguments[0] == "find-generic-password":
            return secrets[arguments[4]]
        if arguments[0] == "delete-generic-password":
            del secrets[arguments[4]]
            return ""
        raise AssertionError(arguments)

    monkeypatch.setattr(manager, "_run", fake_run)
    record = manager.add("hermes-mini", "GitHub", "Repo access", "github-secret", "army-hub")
    assert record["value"] == "••••••••"
    assert "github-secret" not in store.path.read_text()
    assert manager.read("hermes-mini", record["id"]) == "github-secret"
    assert not store.credentials("dsh-mini")
    manager.delete("hermes-mini", record["id"])
    assert not store.credentials("hermes-mini")
    assert not secrets


def test_matrix_profile_update_preserves_avatar_when_only_name_changes(root):
    matrix = MatrixClient(root)
    matrix.request = Mock(return_value=({"displayname": "New Name", "avatar_url": "mxc://existing"}, "application/json"))
    result = matrix.update_profile("hermes-mini", "New Name", None)
    assert result["avatar_url"] == "mxc://existing"
    calls = matrix.request.call_args_list
    assert len(calls) == 2
    assert "displayname" in calls[0].args[1]
    assert "avatar_url" not in calls[0].args[1]


def test_unsupported_credential_test_is_not_marked_valid(root, monkeypatch):
    store = ManagerStore(root)
    manager = CredentialManager(store)
    monkeypatch.setattr(manager, "_run", lambda arguments, secret=None: "")
    record = manager.add("hermes-mini", "Other", "Temporary", "not-a-real-secret")
    result = manager.test("hermes-mini", record["id"])
    assert result["verification"] == "not_tested"
    assert result["last_verified"] is None
    assert "No read-only test" in result["verification_detail"]


def test_reserved_identity_cannot_be_paused_or_lose_its_state(root):
    store = ManagerStore(root)
    record = store.agent("hermes-mini")
    record["status"] = "reserved"
    store.put_agent(record)
    connectors = ConnectorManager(root, store)
    with pytest.raises(RuntimeError, match="no connector"):
        connectors.stop("hermes-mini", pause=True)
    assert store.agent("hermes-mini")["status"] == "reserved"
