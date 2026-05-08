from __future__ import annotations

import threading
import time
from unittest.mock import patch

from fabio_live.async_ops import AsyncOpsWorker


class _DummySheets:
    def log_decision(self, *args, **kwargs):
        return None

    def log_alert(self, *args, **kwargs):
        return None

    def log_trade_entry(self, *args, **kwargs):
        return None

    def log_trade_exit(self, *args, **kwargs):
        return None

    def log_daily_summary(self, *args, **kwargs):
        return None


class _DummyDashboard:
    def append_session(self, *args, **kwargs):
        return None


def test_queue_drops_noncritical_when_full():
    sheets = _DummySheets()
    dash = _DummyDashboard()
    worker = AsyncOpsWorker(sheets, dash, max_queue_size=2)

    gate = threading.Event()

    def slow_task():
        gate.wait(timeout=2.0)

    try:
        worker.enqueue("slow", slow_task)
        worker.enqueue("slow", slow_task)
        worker.enqueue("slow", slow_task)
        worker.enqueue("drop-me", lambda: None)  # should be dropped as non-critical
        time.sleep(0.05)
        health = worker.health()
        assert health["dropped_noncritical"] >= 1
    finally:
        gate.set()
        worker.stop(timeout=2.0)


def test_coalesced_events_keep_latest_payload():
    sheets = _DummySheets()
    dash = _DummyDashboard()
    worker = AsyncOpsWorker(sheets, dash, max_queue_size=5)
    seen: list[int] = []

    def collect(v: int):
        seen.append(v)

    try:
        worker.enqueue("heartbeat", collect, 1, coalesce_key="hb:SPY")
        worker.enqueue("heartbeat", collect, 2, coalesce_key="hb:SPY")
        worker.enqueue("heartbeat", collect, 3, coalesce_key="hb:SPY")
        time.sleep(0.2)
        assert seen == [3]
        assert worker.health()["coalesced_updates"] >= 2
    finally:
        worker.stop(timeout=2.0)


def test_append_dashboard_session_enqueued_as_critical():
    """Full queue must not drop dashboard writes (EOD open positions + trades)."""
    sheets = _DummySheets()
    dash = _DummyDashboard()
    worker = AsyncOpsWorker(sheets, dash, max_queue_size=5)
    try:
        with patch.object(worker, "enqueue", wraps=worker.enqueue) as m:
            worker.append_dashboard_session([], {"date": "2026-01-01"}, [])
            assert m.call_args is not None
            assert m.call_args.kwargs.get("critical") is True
    finally:
        worker.stop(timeout=2.0)
