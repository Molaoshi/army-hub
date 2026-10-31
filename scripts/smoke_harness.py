#!/usr/bin/env python3
"""Run one real ACP model turn without connecting to Matrix."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bridge"))

from army_bridge.acp import SessionManager
from army_bridge.config import AgentSettings

WORKSPACE = ROOT.parent
DSH_LAUNCHER = WORKSPACE / ".runtime" / "dsh-acp.sh"


async def run(harness: str, prompt: str) -> None:
    if harness == "hermes":
        command = [str(Path.home() / ".local" / "bin" / "hermes"), "acp"]
        environment = {"HERMES_ACCEPT_HOOKS": "1"}
    else:
        command = [str(DSH_LAUNCHER)]
        environment = {"NO_BROWSER": "1"}
    settings = AgentSettings(
        agent_id=f"{harness}-smoke",
        display_name=f"{harness} smoke",
        command=command,
        cwd=str(ROOT),
        environment=environment,
    )
    manager = SessionManager(settings, timeout=180)
    try:
        session_id, answer = await manager.prompt("smoke", prompt)
        print(f"session={session_id}")
        print(answer)
    finally:
        await manager.client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("harness", choices=["hermes", "dsh"])
    parser.add_argument("prompt", nargs="?", default="Reply with exactly: ACP smoke passed")
    args = parser.parse_args()
    asyncio.run(run(args.harness, args.prompt))
