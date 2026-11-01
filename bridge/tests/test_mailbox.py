from __future__ import annotations

import pytest

from army_bridge.mailbox import (
    AutomationRateLimit,
    DeliveryStateError,
    DurableMailbox,
    IdempotencyConflict,
)


def enqueue(mailbox: DurableMailbox, key: str = "event-1", source: str = "matrix", **kwargs):
    return mailbox.enqueue(
        source=source,
        idempotency_key=key,
        session_key="root",
        prompt="do work",
        room_id="!room" if source == "matrix" else None,
        thread_root="root" if source == "matrix" else None,
        reply_to=key if source == "matrix" else None,
        **kwargs,
    )


def test_enqueue_is_idempotent_and_queued_controls_are_enforced(tmp_path):
    mailbox = DurableMailbox(tmp_path / "mailbox.db")
    first, created = enqueue(mailbox)
    assert created is True
    same, created = enqueue(mailbox)
    assert created is False
    assert same["id"] == first["id"]

    edited = mailbox.edit_queued(first["id"], "steered work")
    assert edited["prompt"] == "steered work"
    cancelled = mailbox.cancel_queued(first["id"])
    assert cancelled["status"] == "cancelled"
    with pytest.raises(DeliveryStateError):
        mailbox.edit_queued(first["id"], "too late")
    mailbox.close()


def test_conflicting_automation_replay_is_rejected(tmp_path):
    mailbox = DurableMailbox(tmp_path / "mailbox.db")
    enqueue(mailbox, "key", source="automation")
    with pytest.raises(IdempotencyConflict):
        mailbox.enqueue(
            source="automation",
            idempotency_key="key",
            session_key="root",
            prompt="different work",
        )
    mailbox.close()


def test_running_delivery_recovers_as_interrupted_not_queued(tmp_path):
    path = tmp_path / "mailbox.db"
    mailbox = DurableMailbox(path)
    delivery, _ = enqueue(mailbox)
    assert mailbox.claim_next()["status"] == "running"
    mailbox.close()

    recovered = DurableMailbox(path)
    assert recovered.recover_interrupted() == 1
    after = recovered.get(delivery["id"])
    assert after["status"] == "interrupted"
    assert "not retried automatically" in after["error"]
    assert recovered.claim_next() is None
    assert recovered.pending_matrix_notifications()[0]["id"] == delivery["id"]
    recovered.close()


def test_completed_outbox_is_notified_without_reopening_provider_turn(tmp_path):
    path = tmp_path / "mailbox.db"
    mailbox = DurableMailbox(path)
    delivery, _ = enqueue(mailbox)
    mailbox.claim_next()
    mailbox.complete(delivery["id"], "answer")
    mailbox.close()

    recovered = DurableMailbox(path)
    assert recovered.claim_next() is None
    pending = recovered.pending_matrix_notifications()
    assert len(pending) == 1
    assert pending[0]["response"] == "answer"
    recovered.mark_notified(delivery["id"])
    assert recovered.pending_matrix_notifications() == []
    recovered.close()


def test_automation_limit_survives_restart_and_replay_does_not_consume_quota(tmp_path):
    path = tmp_path / "mailbox.db"
    mailbox = DurableMailbox(path)
    enqueue(mailbox, "one", source="automation", automation_rate_limit=1, now=100)
    same, created = enqueue(mailbox, "one", source="automation", automation_rate_limit=1, now=101)
    assert created is False
    with pytest.raises(AutomationRateLimit):
        enqueue(mailbox, "two", source="automation", automation_rate_limit=1, now=102)
    mailbox.close()

    recovered = DurableMailbox(path)
    with pytest.raises(AutomationRateLimit):
        enqueue(recovered, "three", source="automation", automation_rate_limit=1, now=103)
    _, created = enqueue(recovered, "four", source="automation", automation_rate_limit=1, now=3701)
    assert created is True
    recovered.close()
