from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import subprocess
import sys


def test_online_mailbox_backup_is_consistent_and_verified(tmp_path):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    source_path = runtime / "hermes-mini-mailbox.sqlite3"
    source = sqlite3.connect(source_path)
    source.execute("PRAGMA journal_mode=WAL")
    source.execute("CREATE TABLE deliveries(id TEXT PRIMARY KEY, status TEXT)")
    source.execute("INSERT INTO deliveries VALUES ('one', 'completed')")
    source.commit()
    source.close()

    destination = tmp_path / "backup"
    script = Path(__file__).resolve().parents[2] / "scripts" / "backup_mailboxes.py"
    subprocess.run([sys.executable, str(script), str(runtime), str(destination)], check=True)

    restored = sqlite3.connect(destination / source_path.name)
    assert restored.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert restored.execute("SELECT id, status FROM deliveries").fetchall() == [("one", "completed")]
    restored.close()
    manifest = json.loads((destination / "manifest.json").read_text())
    assert manifest["mailboxes"][0]["name"] == source_path.name
    assert manifest["mailboxes"][0]["integrity_check"] == "ok"
