from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from army_grok.config import MatrixSettings, PolicySettings
from army_grok_gateway.config import GatewaySettings, Settings
from army_grok_gateway.connector import GrokGatewayConnector
from army_grok_gateway.gateway import GatewayClient, Reply, turn_entries


def gateway_settings(tmp_path: Path) -> GatewaySettings:
    return GatewaySettings(
        base_url="http://127.0.0.1:1340",
        agent_id="agent-1",
        discovery_path=tmp_path / "gateway.json",
        reply_timeout_seconds=1,
        poll_interval_seconds=0,
        stable_reply_seconds=0,
    )


def test_correlates_exact_nonce_and_stops_before_next_prompt(tmp_path: Path):
    entries = [
        {"id": "old-reply", "kind": "send-message", "message": {"type": "text", "content": "Not yours"}},
        {"id": "prompt", "kind": "message", "role": "user", "clientNonce": "wanted", "requestId": "request-1"},
        {"id": "progress", "kind": "send-message", "requestId": "request-1", "message": {"type": "text", "content": "Working"}},
        {"id": "internal", "kind": "message", "role": "assistant", "toAgent": "research"},
        {"id": "reply", "kind": "send-message", "requestId": "request-1", "message": {"type": "text", "content": "Yours"}},
        {"id": "next", "kind": "message", "role": "user", "clientNonce": "next"},
        {"id": "next-reply", "kind": "send-message", "message": {"type": "text", "content": "Not part of this turn"}},
    ]
    prompt, replies = turn_entries(entries, "wanted")
    assert prompt["clientNonce"] == "wanted"
    assert [entry["id"] for entry in replies] == ["progress", "reply"]
    client = GatewayClient(gateway_settings(tmp_path))
    reply = client._reply(prompt, replies, "Yours")
    assert reply.shared_request_id is True
    assert reply.prompt_request_id == "request-1"


def test_waits_for_exact_reply_after_busy_transition(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    client = GatewayClient(gateway_settings(tmp_path))
    entries = [
        {"id": "prompt", "kind": "message", "clientNonce": "nonce", "requestId": "r1"},
        {"id": "reply", "kind": "send-message", "requestId": "r1", "message": {"type": "text", "content": "Done"}},
    ]
    monkeypatch.setattr(client, "transcript", lambda tail=True: entries)
    monkeypatch.setattr(client, "is_busy", lambda: False)
    reply = client.wait_for_reply("nonce")
    assert reply.text == "Done"
    assert reply.entry_ids == ("reply",)


def connector_settings(tmp_path: Path) -> Settings:
    return Settings(
        matrix=MatrixSettings(
            homeserver="http://127.0.0.1:8010",
            user_id="@grok:army.local",
            access_token="test-only",
            device_id="TEST",
            allowed_users={"@mo:army.local", "@grok:army.local"},
            allowed_rooms={"!room:army.local"},
        ),
        gateway=gateway_settings(tmp_path),
        policy=PolicySettings(min_turn_interval_seconds=0),
        state_path=tmp_path / "state.json",
    )


def message(event_id: str = "$one", body: str = "@grok hello") -> SimpleNamespace:
    return SimpleNamespace(
        event_id=event_id,
        sender="@mo:army.local",
        source={"content": {"msgtype": "m.text", "body": body, "m.mentions": {"user_ids": ["@grok:army.local"]}}},
    )


@pytest.mark.asyncio
async def test_unmentioned_message_is_silent(tmp_path: Path):
    connector = GrokGatewayConnector(connector_settings(tmp_path), gateway=Mock())
    connector.client.room_send = AsyncMock()
    event = message(body="hello without mention")
    event.source["content"]["m.mentions"]["user_ids"] = []
    await connector._process_message("!room:army.local", event)
    connector.gateway.send_prompt.assert_not_called()
    connector.client.room_send.assert_not_called()


@pytest.mark.asyncio
async def test_reply_is_threaded_and_duplicate_event_is_suppressed(tmp_path: Path):
    gateway = Mock()
    gateway.prompt_observed.return_value = False
    gateway.wait_for_reply.return_value = Reply("Remembered", ("reply",), "request", True)
    connector = GrokGatewayConnector(connector_settings(tmp_path), gateway=gateway)
    response = SimpleNamespace(event_id="$reply")
    connector.client.room_send = AsyncMock(return_value=response)
    event = message()
    await connector._process_message("!room:army.local", event)
    await connector._process_message("!room:army.local", event)
    assert gateway.send_prompt.call_count == 1
    content = connector.client.room_send.call_args.args[2]
    assert content["m.relates_to"]["event_id"] == "$one"
    assert content["m.relates_to"]["m.in_reply_to"]["event_id"] == "$one"
    assert connector.client.room_send.call_args.kwargs["tx_id"].startswith("army-grok-gateway-")


@pytest.mark.asyncio
async def test_restart_recovers_accepted_turn_without_duplicate_prompt(tmp_path: Path):
    settings = connector_settings(tmp_path)
    state = {
        "pending_turns": {
            "persisted-nonce": {
                "status": "accepted",
                "room_id": "!room:army.local",
                "thread_root": "$root",
                "reply_to": "$original",
                "agent_turn": 1,
                "sender": "@mo:army.local",
                "text": "@grok remember this",
            }
        }
    }
    import json
    settings.state_path.write_text(json.dumps(state), encoding="utf-8")
    gateway = Mock()
    gateway.wait_for_reply.return_value = Reply("Recovered once", ("reply",), "request", True)
    connector = GrokGatewayConnector(settings, gateway=gateway)
    connector.client.room_send = AsyncMock(return_value=SimpleNamespace(event_id="$reply"))
    await connector.recover_pending()
    gateway.send_prompt.assert_not_called()
    gateway.wait_for_reply.assert_called_once_with("persisted-nonce")
    connector.client.room_send.assert_awaited_once()
    assert connector.state.data["pending_turns"] == {}
    assert connector.state.data["completed_turns"][0]["matrix_event_id"] == "$reply"


@pytest.mark.asyncio
async def test_restart_recovers_created_turn_already_observed_by_gateway(tmp_path: Path):
    settings = connector_settings(tmp_path)
    import json
    settings.state_path.write_text(json.dumps({"pending_turns": {"nonce": {
        "status": "created", "room_id": "!room:army.local", "thread_root": "$root",
        "reply_to": "$original", "agent_turn": 1, "sender": "@mo:army.local", "text": "@grok hello",
    }}}), encoding="utf-8")
    gateway = Mock()
    gateway.prompt_observed.return_value = True
    gateway.wait_for_reply.return_value = Reply("Recovered", ("reply",), None, False)
    connector = GrokGatewayConnector(settings, gateway=gateway)
    connector.client.room_send = AsyncMock(return_value=SimpleNamespace(event_id="$reply"))
    await connector.recover_pending()
    gateway.send_prompt.assert_not_called()
    assert connector.state.data["pending_turns"] == {}


def persisted_failed_turn(settings: Settings, status: str = "failed") -> None:
    import json
    settings.state_path.write_text(json.dumps({"pending_turns": {"nonce": {
        "status": status, "room_id": "!room:army.local", "thread_root": "$root",
        "reply_to": "$original", "agent_turn": 1, "sender": "@mo:army.local", "text": "@grok hello",
    }}}), encoding="utf-8")


@pytest.mark.asyncio
async def test_recovery_resubmits_once_after_preacceptance_failure(tmp_path: Path):
    settings = connector_settings(tmp_path)
    persisted_failed_turn(settings, status="created")
    gateway = Mock()
    gateway.prompt_observed.return_value = False
    gateway.send_prompt.side_effect = RuntimeError("connection dropped before acceptance")
    connector = GrokGatewayConnector(settings, gateway=gateway)
    connector.client.room_send = AsyncMock(return_value=SimpleNamespace(event_id="$notice"))
    await connector.recover_pending()
    assert connector.state.data["pending_turns"]["nonce"]["status"] == "failed"
    gateway.wait_for_reply.assert_not_called()

    gateway.send_prompt.reset_mock()
    gateway.send_prompt.side_effect = None
    gateway.wait_for_reply.return_value = Reply("Recovered", ("reply",), None, False)
    await connector.recover_pending()
    gateway.send_prompt.assert_called_once()
    gateway.wait_for_reply.assert_called_once_with("nonce")
    assert connector.state.data["pending_turns"] == {}


@pytest.mark.asyncio
async def test_recovery_does_not_duplicate_ambiguous_submission_seen_by_gateway(tmp_path: Path):
    settings = connector_settings(tmp_path)
    persisted_failed_turn(settings)
    gateway = Mock()
    gateway.prompt_observed.return_value = True
    gateway.wait_for_reply.return_value = Reply("Recovered", ("reply",), None, False)
    connector = GrokGatewayConnector(settings, gateway=gateway)
    connector.client.room_send = AsyncMock(return_value=SimpleNamespace(event_id="$reply"))
    await connector.recover_pending()
    gateway.send_prompt.assert_not_called()
    gateway.wait_for_reply.assert_called_once_with("nonce")
    assert connector.state.data["pending_turns"] == {}


@pytest.mark.asyncio
async def test_postacceptance_failure_never_returns_turn_to_submission(tmp_path: Path):
    settings = connector_settings(tmp_path)
    persisted_failed_turn(settings, status="accepted")
    gateway = Mock()
    gateway.wait_for_reply.side_effect = RuntimeError("temporary transcript failure")
    connector = GrokGatewayConnector(settings, gateway=gateway)
    connector.client.room_send = AsyncMock(return_value=SimpleNamespace(event_id="$notice"))
    await connector.recover_pending()
    assert connector.state.data["pending_turns"]["nonce"]["status"] == "accepted"
    gateway.send_prompt.assert_not_called()
    gateway.prompt_observed.assert_not_called()
