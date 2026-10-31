from pathlib import Path
import sys

import pytest

from army_bridge.acp import SessionManager
from army_bridge.config import AgentSettings


@pytest.mark.asyncio
async def test_acp_session_prompt_and_reuse():
    fake = Path(__file__).with_name("fake_acp.py")
    settings = AgentSettings(
        agent_id="fake",
        display_name="Fake",
        command=[sys.executable, str(fake)],
        cwd=str(Path(__file__).parent),
    )
    manager = SessionManager(settings, timeout=10)
    try:
        session_id, answer = await manager.prompt("root", "first")
        assert session_id == "session-1"
        assert answer == "ack:first"
        second_id, answer = await manager.prompt("root", "second")
        assert second_id == session_id
        assert answer == "ack:second"
        third_id, _ = await manager.prompt("other-root", "third")
        assert third_id == "session-2"
    finally:
        await manager.client.close()


@pytest.mark.asyncio
async def test_acp_process_restart_reloads_saved_session():
    fake = Path(__file__).with_name("fake_acp.py")
    settings = AgentSettings(
        agent_id="fake",
        display_name="Fake",
        command=[sys.executable, str(fake)],
        cwd=str(Path(__file__).parent),
    )
    manager = SessionManager(settings, timeout=10)
    try:
        session_id, _ = await manager.prompt("root", "first")
        await manager.client.close()
        second_id, answer = await manager.prompt("root", "after restart")
        assert second_id == session_id
        assert answer == "ack:after restart"
        assert manager.client.generation == 2
    finally:
        await manager.client.close()
