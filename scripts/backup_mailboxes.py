#!/usr/bin/env python3
"""Create consistent online backups of Army Hub SQLite mailboxes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import sys


def backup_mailboxes(runtime: Path, destination: Path) -> list[dict[str, object]]:
    destination.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    for source_path in sorted(runtime.glob("*-mailbox.sqlite3")):
        target_path = destination / source_path.name
        source = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
        target = sqlite3.connect(target_path)
        try:
            source.backup(target)
            result = target.execute("PRAGMA integrity_check").fetchone()
            if result is None or result[0] != "ok":
                raise RuntimeError(f"integrity check failed for {source_path.name}")
        finally:
            target.close()
            source.close()
        payload = target_path.read_bytes()
        records.append(
            {
                "name": source_path.name,
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "integrity_check": "ok",
            }
        )
    manifest = destination / "manifest.json"
    manifest.write_text(json.dumps({"mailboxes": records}, indent=2) + "\n", encoding="utf-8")
    return records


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: backup_mailboxes.py RUNTIME_DIRECTORY DESTINATION_DIRECTORY")
    records = backup_mailboxes(Path(sys.argv[1]), Path(sys.argv[2]))
    print(f"Backed up and verified {len(records)} mailbox database(s)")


if __name__ == "__main__":
    main()
