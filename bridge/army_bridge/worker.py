from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable

from .acp import SessionManager
from .bridge_state import BridgeState
from .config import PolicySettings
from .mailbox import DurableMailbox


LOG = logging.getLogger(__name__)
Notifier = Callable[[dict[str, Any]], Awaitable[None]]


def safe_error(error: Exception) -> str:
    text = str(error).replace("\n", " ")
    return text[:300] if text else error.__class__.__name__


def bounded_turn_delay(last_turn_at: float, interval: float, now: float) -> float:
    elapsed = now - float(last_turn_at)
    return min(interval, max(0.0, interval - elapsed))


class DeliveryWorker:
    """One serialized provider lane and a durable Matrix outbox per agent."""

    def __init__(
        self,
        *,
        mailbox: DurableMailbox,
        sessions: SessionManager,
        state: BridgeState,
        policy: PolicySettings,
        notifier: Notifier,
    ):
        self.mailbox = mailbox
        self.sessions = sessions
        self.state = state
        self.policy = policy
        self.notifier = notifier
        self._wake = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._stopping = False

    def wake(self) -> None:
        self._wake.set()

    async def start(self) -> None:
        if self._task is not None:
            return
        recovered = self.mailbox.recover_interrupted()
        if recovered:
            LOG.warning("Marked %s uncertain deliveries interrupted during recovery", recovered)
        self._stopping = False
        self._task = asyncio.create_task(self._run(), name="army-delivery-worker")

    async def stop(self) -> None:
        self._stopping = True
        task = self._task
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            self._task = None

    async def _run(self) -> None:
        while not self._stopping:
            try:
                self._wake.clear()
                if await self._notify_one():
                    continue
                delivery = self.mailbox.claim_next()
                if delivery is None:
                    await self._wake.wait()
                    continue
                await self._execute(delivery)
            except asyncio.CancelledError:
                raise
            except Exception:
                LOG.exception("Delivery worker failed; retrying after a short delay")
                await asyncio.sleep(2)

    async def _execute(self, delivery: dict[str, Any]) -> None:
        delay = bounded_turn_delay(
            self.state.data.get("last_turn_at", 0),
            self.policy.min_turn_interval_seconds,
            time.time(),
        )
        if delay:
            await asyncio.sleep(delay)
        try:
            session_key = delivery["session_key"]
            session_id, answer = await self.sessions.prompt(
                session_key,
                delivery["prompt"],
                self.state.data["sessions"].get(session_key),
            )
            self.state.data["sessions"][session_key] = session_id
            self.state.data["last_turn_at"] = time.time()
            self.state.save()
            self.mailbox.complete(delivery["id"], answer)
        except asyncio.CancelledError:
            self.mailbox.interrupt(
                delivery["id"],
                "Bridge stopped while this delivery was running; it was not retried automatically.",
            )
            raise
        except Exception as error:
            LOG.exception("Agent turn failed for delivery %s", delivery["id"])
            self.mailbox.fail(delivery["id"], safe_error(error))

    async def _notify_one(self) -> bool:
        pending = self.mailbox.pending_matrix_notifications()
        if not pending:
            return False
        delivery = pending[0]
        try:
            await self.notifier(delivery)
            self.mailbox.mark_notified(delivery["id"])
        except asyncio.CancelledError:
            raise
        except Exception:
            LOG.exception("Matrix notification failed for %s; provider turn will not be repeated", delivery["id"])
            await asyncio.sleep(5)
        return True
