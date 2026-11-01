from __future__ import annotations

from contextlib import contextmanager
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4


TERMINAL_STATUSES = {"completed", "failed", "interrupted", "cancelled"}


class MailboxError(RuntimeError):
    pass


class DeliveryStateError(MailboxError):
    pass


class IdempotencyConflict(MailboxError):
    pass


class AutomationRateLimit(MailboxError):
    def __init__(self, retry_after: int):
        super().__init__(f"automation rate limit exceeded; retry in {retry_after} seconds")
        self.retry_after = retry_after


class DurableMailbox:
    """Small synchronous SQLite store used only from the bridge event loop."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS deliveries (
                id TEXT PRIMARY KEY,
                idempotency_key TEXT NOT NULL UNIQUE,
                source TEXT NOT NULL CHECK(source IN ('matrix', 'automation')),
                status TEXT NOT NULL CHECK(status IN ('queued', 'running', 'completed', 'failed', 'interrupted', 'cancelled')),
                session_key TEXT NOT NULL,
                prompt TEXT NOT NULL,
                room_id TEXT,
                thread_root TEXT,
                reply_to TEXT,
                agent_turn INTEGER NOT NULL DEFAULT 0,
                response TEXT,
                error TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                ended_at REAL,
                notified_at REAL
            );
            CREATE INDEX IF NOT EXISTS deliveries_queue
                ON deliveries(status, created_at);
            CREATE INDEX IF NOT EXISTS deliveries_notifications
                ON deliveries(source, status, notified_at);
            CREATE TABLE IF NOT EXISTS automation_requests (
                requested_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS automation_requests_time
                ON automation_requests(requested_at);
            """
        )
        self.path.chmod(0o600)

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield self.db
        except Exception:
            self.db.execute("ROLLBACK")
            raise
        else:
            self.db.execute("COMMIT")

    @staticmethod
    def _delivery(row: sqlite3.Row | None) -> dict[str, Any] | None:
        return dict(row) if row is not None else None

    def enqueue(
        self,
        *,
        source: str,
        idempotency_key: str,
        session_key: str,
        prompt: str,
        room_id: str | None = None,
        thread_root: str | None = None,
        reply_to: str | None = None,
        agent_turn: int = 0,
        automation_rate_limit: int | None = None,
        now: float | None = None,
    ) -> tuple[dict[str, Any], bool]:
        timestamp = time.time() if now is None else now
        delivery_id = uuid4().hex
        with self.transaction() as db:
            existing = db.execute(
                "SELECT * FROM deliveries WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            if existing is not None:
                if source == "automation" and (
                    existing["prompt"] != prompt or existing["session_key"] != session_key
                ):
                    raise IdempotencyConflict("idempotency key was already used with different content")
                return self._delivery(existing), False  # type: ignore[return-value]

            if source == "automation" and automation_rate_limit is not None:
                cutoff = timestamp - 3600
                db.execute("DELETE FROM automation_requests WHERE requested_at <= ?", (cutoff,))
                count = db.execute("SELECT COUNT(*) FROM automation_requests").fetchone()[0]
                if count >= automation_rate_limit:
                    oldest = db.execute(
                        "SELECT MIN(requested_at) FROM automation_requests"
                    ).fetchone()[0]
                    retry_after = max(1, int(oldest + 3600 - timestamp + 0.999))
                    raise AutomationRateLimit(retry_after)
                db.execute("INSERT INTO automation_requests(requested_at) VALUES (?)", (timestamp,))

            db.execute(
                """
                INSERT INTO deliveries(
                    id, idempotency_key, source, status, session_key, prompt,
                    room_id, thread_root, reply_to, agent_turn, created_at, updated_at
                ) VALUES (?, ?, ?, 'queued', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    delivery_id,
                    idempotency_key,
                    source,
                    session_key,
                    prompt,
                    room_id,
                    thread_root,
                    reply_to,
                    agent_turn,
                    timestamp,
                    timestamp,
                ),
            )
        return self.get(delivery_id), True  # type: ignore[return-value]

    def get(self, delivery_id: str) -> dict[str, Any] | None:
        return self._delivery(
            self.db.execute("SELECT * FROM deliveries WHERE id = ?", (delivery_id,)).fetchone()
        )

    def pending(self) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT * FROM deliveries WHERE status IN ('queued', 'running') ORDER BY created_at"
        ).fetchall()
        return [dict(row) for row in rows]

    def recover_interrupted(self, *, now: float | None = None) -> int:
        timestamp = time.time() if now is None else now
        with self.transaction() as db:
            cursor = db.execute(
                """
                UPDATE deliveries
                SET status = 'interrupted', error = ?, updated_at = ?, ended_at = ?
                WHERE status = 'running'
                """,
                (
                    "Bridge stopped before this delivery reached a confirmed terminal state; it was not retried automatically.",
                    timestamp,
                    timestamp,
                ),
            )
        return cursor.rowcount

    def claim_next(self, *, now: float | None = None) -> dict[str, Any] | None:
        timestamp = time.time() if now is None else now
        with self.transaction() as db:
            row = db.execute(
                "SELECT id FROM deliveries WHERE status = 'queued' ORDER BY created_at LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            db.execute(
                "UPDATE deliveries SET status = 'running', updated_at = ? WHERE id = ?",
                (timestamp, row["id"]),
            )
        return self.get(row["id"])

    def _finish(self, delivery_id: str, status: str, **fields: Any) -> None:
        if status not in TERMINAL_STATUSES:
            raise ValueError(status)
        now = time.time()
        assignments = ["status = ?", "updated_at = ?", "ended_at = ?"]
        values: list[Any] = [status, now, now]
        for name, value in fields.items():
            assignments.append(f"{name} = ?")
            values.append(value)
        values.append(delivery_id)
        with self.transaction() as db:
            db.execute(
                f"UPDATE deliveries SET {', '.join(assignments)} WHERE id = ? AND status = 'running'",
                values,
            )

    def complete(self, delivery_id: str, response: str) -> None:
        self._finish(delivery_id, "completed", response=response, error=None)

    def fail(self, delivery_id: str, error: str) -> None:
        self._finish(delivery_id, "failed", error=error)

    def interrupt(self, delivery_id: str, reason: str) -> None:
        self._finish(delivery_id, "interrupted", error=reason)

    def edit_queued(self, delivery_id: str, prompt: str) -> dict[str, Any]:
        with self.transaction() as db:
            cursor = db.execute(
                "UPDATE deliveries SET prompt = ?, updated_at = ? WHERE id = ? AND status = 'queued'",
                (prompt, time.time(), delivery_id),
            )
            if cursor.rowcount != 1:
                raise DeliveryStateError("only a queued delivery can be edited")
        return self.get(delivery_id)  # type: ignore[return-value]

    def cancel_queued(self, delivery_id: str) -> dict[str, Any]:
        now = time.time()
        with self.transaction() as db:
            cursor = db.execute(
                """
                UPDATE deliveries
                SET status = 'cancelled', updated_at = ?, ended_at = ?
                WHERE id = ? AND status = 'queued'
                """,
                (now, now, delivery_id),
            )
            if cursor.rowcount != 1:
                raise DeliveryStateError("only a queued delivery can be cancelled")
        return self.get(delivery_id)  # type: ignore[return-value]

    def pending_matrix_notifications(self) -> list[dict[str, Any]]:
        rows = self.db.execute(
            """
            SELECT * FROM deliveries
            WHERE source = 'matrix'
              AND status IN ('completed', 'failed', 'interrupted')
              AND notified_at IS NULL
            ORDER BY created_at
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def mark_notified(self, delivery_id: str) -> None:
        with self.transaction() as db:
            db.execute(
                "UPDATE deliveries SET notified_at = ? WHERE id = ? AND notified_at IS NULL",
                (time.time(), delivery_id),
            )

    def close(self) -> None:
        self.db.close()
