from pathlib import Path
import sys

import pytest
from unittest.mock import AsyncMock

from army_bridge.acp import AcpClient, AcpError, SessionManager
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


@pytest.mark.asyncio
async def test_acp_applies_model_then_dependent_effort():
    settings = AgentSettings(
        agent_id="opencode", display_name="OpenCode", command=["opencode", "acp"], cwd="/tmp",
        session_config={"model": "opencode/flash", "effort": "high"},
    )
    client = AcpClient(settings)
    initial = [
        {"id": "model", "options": [{"value": "opencode/flash"}]},
        {"id": "effort", "options": [{"value": "high"}]},
    ]
    client.request = AsyncMock(side_effect=[
        {"sessionId": "session-1", "configOptions": initial},
        {"configOptions": [
            {"id": "model", "currentValue": "opencode/flash"},
            {"id": "effort", "options": [{"value": "high"}]},
        ]},
        {"configOptions": [
            {"id": "model", "currentValue": "opencode/flash"},
            {"id": "effort", "currentValue": "high"},
        ]},
    ])
    assert await client.new_session() == "session-1"
    assert [call.args[0] for call in client.request.call_args_list] == [
        "session/new", "session/set_config_option", "session/set_config_option",
    ]
    assert client.request.call_args_list[1].args[1]["configId"] == "model"
    assert client.request.call_args_list[2].args[1]["configId"] == "effort"


@pytest.mark.asyncio
async def test_acp_rejects_unapplied_model_selection():
    settings = AgentSettings(
        agent_id="opencode", display_name="OpenCode", command=["opencode", "acp"], cwd="/tmp",
        session_config={"model": "opencode/flash"},
    )
    client = AcpClient(settings)
    client.request = AsyncMock(side_effect=[
        {"sessionId": "session-1", "configOptions": [{"id": "model", "options": [{"value": "opencode/flash"}]}]},
        {"configOptions": [{"id": "model", "currentValue": "opencode/other"}]},
    ])
    with pytest.raises(AcpError, match="did not apply"):
        await client.new_session()
