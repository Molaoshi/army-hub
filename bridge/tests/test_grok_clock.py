from __future__ import annotations

from army_grok.connector import _bounded_turn_delay


def test_restored_future_timestamp_has_bounded_delay():
    assert _bounded_turn_delay(last_turn_at=2_000_000_000.0, interval=2.0, now=1_800_000_000.0) == 2.0


def test_legacy_monotonic_timestamp_does_not_delay_after_reboot():
    assert _bounded_turn_delay(last_turn_at=12_345.0, interval=2.0, now=1_800_000_000.0) == 0.0
