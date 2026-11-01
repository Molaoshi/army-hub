from __future__ import annotations

import asyncio
import json
from pathlib import Path
import stat
import sys
from unittest.mock import AsyncMock

import pytest

from army_bridge.acp import SessionManager
from army_bridge.automation import AutomationServer
from army_bridge.automation_cli import request
from army_bridge.bridge_state import BridgeState
from army_bridge.config import AgentSettings, AutomationSettings, PolicySettings
from army_bridge.mailbox import DurableMailbox
from army_bridge.worker import DeliveryWorker


def agent_settings() -> AgentSettings:
    return AgentSettings(
        agent_id="fake",
        display_name="Fake Agent",
        command=[sys.executable, str(Path(__file__).with_name("fake_acp.py"))],
        cwd=str(Path(__file__).parent),
    )


async def call(runtime_root: Path, method: str, path: str, payload: dict | None = None):
    return await asyncio.to_thread(request, runtime_root, "fake", method, path, payload)


async def raw_http(port: int, headers: dict[str, str], body: bytes = b""):
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(b"POST /v1/agents/fake/messages HTTP/1.1\r\n")
    for name, value in headers.items():
        writer.write(f"{name}: {value}\r\n".encode())
    writer.write(f"Content-Length: {len(body)}\r\n\r\n".encode() + body)
    await writer.drain()
    response = await reader.read()
    writer.close()
    await writer.wait_closed()
    first_line, _, remainder = response.partition(b"\r\n")
    status = int(first_line.split()[1])
    payload = json.loads(remainder.split(b"\r\n\r\n", 1)[1])
    return status, payload


@pytest.mark.asyncio
async def test_automation_turn_idempotency_and_owner_files(tmp_path):
    runtime_root = tmp_path / "automation"
    mailbox = DurableMailbox(tmp_path / "mailbox.db")
    sessions = SessionManager(agent_settings(), timeout=10)
    worker = DeliveryWorker(
        mailbox=mailbox,
        sessions=sessions,
        state=BridgeState(tmp_path / "state.json"),
        policy=PolicySettings(min_turn_interval_seconds=0),
        notifier=AsyncMock(),
    )
    server = AutomationServer(
        settings=AutomationSettings(enabled=True, state_dir=runtime_root / "fake"),
        agent=agent_settings(),
        mailbox=mailbox,
        on_enqueue=worker.wake,
    )
    await worker.start()
    await server.start()
    try:
        agents = await call(runtime_root, "GET", "/v1/agents")
        assert agents["agents"][0]["id"] == "fake"
        assert stat.S_IMODE((runtime_root / "fake").stat().st_mode) == 0o700
        assert stat.S_IMODE((runtime_root / "fake" / "token").stat().st_mode) == 0o600

        sent = await call(
            runtime_root,
            "POST",
            "/v1/agents/fake/messages",
            {"text": "hello from Buzz", "conversation_id": "buzz", "idempotency_key": "buzz-1"},
        )
        assert sent["created"] is True
        assert sent["session_key"] == "automation:buzz"
        replay = await call(
            runtime_root,
            "POST",
            "/v1/agents/fake/messages",
            {"text": "hello from Buzz", "conversation_id": "buzz", "idempotency_key": "buzz-1"},
        )
        assert replay["created"] is False
        assert replay["id"] == sent["id"]

        for _ in range(100):
            status = await call(runtime_root, "GET", f"/v1/agents/fake/deliveries/{sent['id']}")
            if status["status"] == "completed":
                break
            await asyncio.sleep(0.02)
        assert status["status"] == "completed"
        assert "hello from Buzz" in status["response"]
    finally:
        await server.stop()
        await worker.stop()
        await sessions.client.close()
        mailbox.close()
    assert not (runtime_root / "fake" / "token").exists()
    assert not (runtime_root / "fake" / "url").exists()


@pytest.mark.asyncio
async def test_automation_rejects_browser_foreign_host_bad_auth_and_large_body(tmp_path):
    runtime_root = tmp_path / "automation"
    mailbox = DurableMailbox(tmp_path / "mailbox.db")
    server = AutomationServer(
        settings=AutomationSettings(enabled=True, state_dir=runtime_root / "fake", body_limit_bytes=32),
        agent=agent_settings(),
        mailbox=mailbox,
        on_enqueue=lambda: None,
    )
    await server.start()
    token = (runtime_root / "fake" / "token").read_text().strip()
    auth = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    host = {"Host": f"127.0.0.1:{server.port}"}
    try:
        status, _ = await raw_http(server.port, host)
        assert status == 401
        status, _ = await raw_http(server.port, {**host, **auth, "Origin": "https://evil.example"}, b"{}")
        assert status == 403
        status, _ = await raw_http(server.port, {**auth, "Host": f"localhost:{server.port}"}, b"{}")
        assert status == 403
        status, _ = await raw_http(server.port, {**host, **auth}, b"x" * 33)
        assert status == 413
    finally:
        await server.stop()
        mailbox.close()


@pytest.mark.asyncio
async def test_automation_queued_edit_cancel_and_persistent_rate_limit(tmp_path):
    runtime_root = tmp_path / "automation"
    mailbox = DurableMailbox(tmp_path / "mailbox.db")
    server = AutomationServer(
        settings=AutomationSettings(enabled=True, state_dir=runtime_root / "fake", runs_per_hour=1),
        agent=agent_settings(),
        mailbox=mailbox,
        on_enqueue=lambda: None,
    )
    await server.start()
    try:
        sent = await call(
            runtime_root,
            "POST",
            "/v1/agents/fake/messages",
            {"text": "initial", "idempotency_key": "one"},
        )
        edited = await call(
            runtime_root,
            "PATCH",
            f"/v1/agents/fake/deliveries/{sent['id']}",
            {"text": "steered"},
        )
        assert edited["status"] == "queued"
        cancelled = await call(
            runtime_root, "POST", f"/v1/agents/fake/deliveries/{sent['id']}/cancel", {}
        )
        assert cancelled["status"] == "cancelled"
        with pytest.raises(RuntimeError, match="rate limit"):
            await call(
                runtime_root,
                "POST",
                "/v1/agents/fake/messages",
                {"text": "second", "idempotency_key": "two"},
            )
    finally:
        await server.stop()
        mailbox.close()


@pytest.mark.asyncio
async def test_recovery_notifies_interrupted_without_calling_provider(tmp_path):
    mailbox = DurableMailbox(tmp_path / "mailbox.db")
    delivery, _ = mailbox.enqueue(
        source="matrix",
        idempotency_key="$event",
        session_key="$event",
        prompt="work",
        room_id="!room",
        thread_root="$event",
        reply_to="$event",
        agent_turn=1,
    )
    mailbox.claim_next()
    sessions = AsyncMock()
    notifier = AsyncMock()
    worker = DeliveryWorker(
        mailbox=mailbox,
        sessions=sessions,
        state=BridgeState(tmp_path / "state.json"),
        policy=PolicySettings(min_turn_interval_seconds=0),
        notifier=notifier,
    )
    await worker.start()
    for _ in range(100):
        if notifier.await_count:
            break
        await asyncio.sleep(0.01)
    await worker.stop()
    notified = notifier.await_args.args[0]
    assert notified["id"] == delivery["id"]
    assert notified["status"] == "interrupted"
    sessions.prompt.assert_not_called()
    mailbox.close()


@pytest.mark.asyncio
async def test_matrix_event_uses_same_durable_lane_and_transaction_id(tmp_path):
    from types import SimpleNamespace

    from army_bridge.bridge import ArmyBridge
    from army_bridge.config import MatrixSettings, Settings

    settings = Settings(
        matrix=MatrixSettings(
            homeserver="http://127.0.0.1:8010",
            user_id="@fake:army.local",
            access_token="test-only",
            device_id="TEST",
            allowed_users={"@mo:army.local"},
            allowed_rooms={"!room:army.local"},
        ),
        agent=agent_settings(),
        policy=PolicySettings(min_turn_interval_seconds=0),
        state_path=tmp_path / "state.json",
        mailbox_path=tmp_path / "mailbox.db",
    )
    bridge = ArmyBridge(settings)
    bridge.client.room_send = AsyncMock(return_value=SimpleNamespace(event_id="$answer"))
    event = SimpleNamespace(
        event_id="$event",
        sender="@mo:army.local",
        source={
            "content": {
                "msgtype": "m.text",
                "body": "@fake hello",
                "m.mentions": {"user_ids": ["@fake:army.local"]},
            }
        },
    )
    await bridge.worker.start()
    try:
        await bridge._process_message("!room:army.local", event)
        for _ in range(100):
            if bridge.client.room_send.await_count:
                break
            await asyncio.sleep(0.02)
        assert bridge.client.room_send.await_count == 1
        args = bridge.client.room_send.await_args.args
        assert args[0] == "!room:army.local"
        assert args[2]["body"] and "hello" in args[2]["body"]
        delivery_id = bridge.client.room_send.await_args.kwargs["tx_id"]
        assert bridge.mailbox.get(delivery_id)["status"] == "completed"
        assert bridge.mailbox.get(delivery_id)["notified_at"] is not None

        await bridge._process_message("!room:army.local", event)
        count = bridge.mailbox.db.execute("SELECT COUNT(*) FROM deliveries").fetchone()[0]
        assert count == 1
        assert bridge.client.room_send.await_count == 1
    finally:
        await bridge.close()
