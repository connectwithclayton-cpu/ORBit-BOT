"""Tests for telegram command routing (pause / resume / status)."""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

import telegram_bot as tg


@pytest.fixture(autouse=True)
def _reset_telegram_globals():
    yield
    tg._risk_ref = None
    tg._execution_ref = None
    tg._stop_pending_until_by_chat.clear()
    tg._last_cmd_ts_by_chat.clear()


def test_dispatch_resume_clears_flags_and_diagnostics(monkeypatch):
    monkeypatch.setattr(tg, "alert_personal", lambda *_args, **_kw: None)

    class FakeRisk:
        def __init__(self):
            self.paused = True
            self.stopped = True
            self.cleared = False

        def clear_pause_diagnostics(self):
            self.cleared = True

    r = FakeRisk()
    tg._risk_ref = r
    tg.dispatch_authorized_command("/resume", "1", time.time())
    assert r.paused is False
    assert r.stopped is False
    assert r.cleared is True


def test_dispatch_pause_uses_manual_pause_hook_when_present(monkeypatch):
    monkeypatch.setattr(tg, "alert_personal", lambda *_args, **_kw: None)
    hook_calls = []

    class FakeRisk:
        def set_operator_manual_pause(self):
            hook_calls.append(1)

    tg._risk_ref = FakeRisk()
    tg.dispatch_authorized_command("/pause", "1", time.time())
    assert hook_calls == [1]


def test_dispatch_pause_sets_paused_without_hook(monkeypatch):
    monkeypatch.setattr(tg, "alert_personal", lambda *_args, **_kw: None)
    r = SimpleNamespace(paused=False)
    tg._risk_ref = r
    tg.dispatch_authorized_command("/pause", "1", time.time())
    assert r.paused is True


def test_dispatch_status_uses_status_summary(monkeypatch):
    captured = {}

    def cap(msg):
        captured["txt"] = msg

    monkeypatch.setattr(tg, "alert_personal", cap)
    tg._risk_ref = SimpleNamespace(status_summary=lambda: "FAKE_SUMMARY_LINE")
    tg.dispatch_authorized_command("/status", "1", time.time())
    assert "FAKE_SUMMARY_LINE" in captured["txt"]
