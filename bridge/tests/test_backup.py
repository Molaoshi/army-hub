from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import subprocess
import sys


def create_mailbox(path: Path, delivery_id: str) -> None:
    source = sqlite3.connect(path)
    source.execute("PRAGMA journal_mode=WAL")
    source.execute("CREATE TABLE deliveries(id TEXT PRIMARY KEY, status TEXT)")
    source.execute("INSERT INTO deliveries VALUES (?, 'completed')", (delivery_id,))
    source.commit()
    source.close()


def test_online_mailbox_backup_supports_legacy_and_manager_default_names(tmp_path):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    legacy_path = runtime / "hermes-mini-mailbox.sqlite3"
    manager_path = runtime / "new-agent-state.mailbox.sqlite3"
    create_mailbox(legacy_path, "legacy")
    create_mailbox(manager_path, "manager-default")

    destination = tmp_path / "backup"
    script = Path(__file__).resolve().parents[2] / "scripts" / "backup_mailboxes.py"
    subprocess.run([sys.executable, str(script), str(runtime), str(destination)], check=True)

    manifest = json.loads((destination / "manifest.json").read_text())
    assert [record["name"] for record in manifest["mailboxes"]] == [
        "hermes-mini-mailbox.sqlite3",
        "new-agent-state.mailbox.sqlite3",
    ]
    assert all(record["integrity_check"] == "ok" for record in manifest["mailboxes"])

    restored = sqlite3.connect(destination / manager_path.name)
    assert restored.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert restored.execute("SELECT id, status FROM deliveries").fetchall() == [
        ("manager-default", "completed")
    ]
    restored.close()


def test_online_mailbox_backup_rejects_expected_runtime_without_mailboxes(tmp_path):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "new-agent-state.json").write_text("{}")

    script = Path(__file__).resolve().parents[2] / "scripts" / "backup_mailboxes.py"
    result = subprocess.run(
        [sys.executable, str(script), str(runtime), str(tmp_path / "backup")],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "no recognized mailbox databases" in result.stderr
