from __future__ import annotations

import os
import signal
from unittest.mock import Mock

import pytest

from army_manager.connectors import ConnectorError, ConnectorManager
from army_manager.store import ManagerStore


def test_forced_shutdown_targets_only_selected_connector(root, monkeypatch):
    store = ManagerStore(root)
    manager = ConnectorManager(root, store)
    manager.pid_path("hermes-mini").write_text("4321", encoding="utf-8")
    alive = {"selected": True}

    def fake_pid(agent_id):
        return 4321 if agent_id == "hermes-mini" and alive["selected"] else None

    kill = Mock()
    killpg = Mock(side_effect=lambda pgid, sig: alive.update(selected=False))
    monkeypatch.setattr(manager, "pid", fake_pid)
    monkeypatch.setattr(os, "kill", kill)
    monkeypatch.setattr(os, "getpgid", lambda pid: 4321)
    monkeypatch.setattr(os, "killpg", killpg)
    monkeypatch.setattr("army_manager.connectors.time.sleep", lambda seconds: None)

    result = manager.stop("hermes-mini", pause=True)
    kill.assert_called_once_with(4321, signal.SIGTERM)
    killpg.assert_called_once_with(4321, signal.SIGKILL)
    assert not manager.pid_path("hermes-mini").exists()
    assert result["status"] == "paused"
    assert store.agent("dsh-mini")["status"] == "active"


def test_failed_forced_shutdown_retains_pid_for_retry(root, monkeypatch):
    store = ManagerStore(root)
    manager = ConnectorManager(root, store)
    manager.pid_path("hermes-mini").write_text("4321", encoding="utf-8")
    monkeypatch.setattr(manager, "pid", lambda agent_id: 4321)
    monkeypatch.setattr(os, "kill", Mock())
    monkeypatch.setattr(os, "getpgid", lambda pid: 4321)
    monkeypatch.setattr(os, "killpg", Mock())
    monkeypatch.setattr("army_manager.connectors.time.sleep", lambda seconds: None)

    with pytest.raises(ConnectorError, match="PID state retained"):
        manager.stop("hermes-mini")
    assert manager.pid_path("hermes-mini").read_text(encoding="utf-8") == "4321"
