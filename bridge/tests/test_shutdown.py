from __future__ import annotations

import asyncio
from pathlib import Path
import sys
from unittest.mock import AsyncMock

import pytest

from army_bridge.acp import AcpClient
from army_bridge.bridge import ArmyBridge, _bounded_turn_delay
from army_bridge.config import AgentSettings, MatrixSettings, PolicySettings, Settings


def agent_settings(agent_id: str = "fake") -> AgentSettings:
    fake = Path(__file__).with_name("fake_hanging_acp.py")
    return AgentSettings(
        agent_id=agent_id,
        display_name=agent_id,
        command=[sys.executable, str(fake)],
        cwd=str(Path(__file__).parent),
    )


def bridge_settings(tmp_path: Path) -> Settings:
    return Settings(
        matrix=MatrixSettings(
            homeserver="http://127.0.0.1:8010",
            user_id="@fake:army.local",
            access_token="test-only",
            device_id="TEST",
            allowed_users={"@mo:army.local"},
            allowed_rooms={"!room:army.local"},
        ),
        agent=agent_settings(),
        policy=PolicySettings(),
        state_path=tmp_path / "bridge-state.json",
    )


@pytest.mark.asyncio
async def test_stop_interrupts_idle_matrix_long_poll(tmp_path: Path):
    bridge = ArmyBridge(bridge_settings(tmp_path))

    async def long_poll(**kwargs):
        await asyncio.sleep(30)

    bridge.client.sync = AsyncMock(side_effect=long_poll)
    bridge.client.close = AsyncMock()
    bridge.sessions.client.close = AsyncMock()
    task = asyncio.create_task(bridge.run())
    await asyncio.sleep(0.05)
    bridge.stop()
    await asyncio.wait_for(task, timeout=1)
    bridge.client.sync.assert_awaited_once()
    bridge.sessions.client.close.assert_awaited_once()
    bridge.client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_cancels_active_prompt_and_only_terminates_own_child():
    first = AcpClient(agent_settings("first"))
    second = AcpClient(agent_settings("second"))
    await first.start()
    await second.start()
    try:
        session_id = await first.new_session()
        prompt_task = asyncio.create_task(first.prompt(session_id, "wait forever"))
        await asyncio.sleep(0.05)
        first_process = first.process
        second_process = second.process
        assert first_process and second_process
        await asyncio.wait_for(first.close(), timeout=2)
        with pytest.raises(asyncio.CancelledError):
            await prompt_task
        assert first_process.returncode is not None
        assert second_process.returncode is None
        assert first.pending == {}
    finally:
        await first.close()
        await second.close()


def test_restored_pre_reboot_timestamp_cannot_cause_long_sleep():
    assert _bounded_turn_delay(last_turn_at=2_000_000_000.0, interval=2.0, now=1_800_000_000.0) == 2.0
    assert _bounded_turn_delay(last_turn_at=12_345.0, interval=2.0, now=1_800_000_000.0) == 0.0
