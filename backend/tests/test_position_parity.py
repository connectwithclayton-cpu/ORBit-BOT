from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from fabio_live.bot import (
    OPS_ALERT_COOLDOWN_SEC,
    ORBBot,
    compute_position_parity_state,
)

_FABIO = {"SPY", "QQQ"}
_CODE_SPY_CALL = "US.SPY260507C00735000"


def test_parity_ok_when_broker_and_tracked_agree():
    df = pd.DataFrame({"code": [_CODE_SPY_CALL], "qty": [2]})
    tracked = {
        "SPY": {
            "direction": "CALL",
            "code": _CODE_SPY_CALL,
            "remaining_qty": 2,
        }
    }
    st = compute_position_parity_state(df, tracked, _FABIO)
    assert st["parity_ok"] is True
    assert st["ok"] is True
    assert st["query_ok"] is True
    assert st["drift_count"] == 0


def test_parity_drift_tracked_but_missing_broker():
    df = pd.DataFrame(columns=["code", "qty"])
    tracked = {"SPY": {"code": _CODE_SPY_CALL, "remaining_qty": 2}}
    st = compute_position_parity_state(df, tracked, _FABIO)
    assert st["parity_ok"] is False
    assert len(st["drifts"]) == 1
    assert st["drifts"][0]["code"] == _CODE_SPY_CALL
    assert st["drifts"][0]["broker_qty"] == 0
    assert st["drifts"][0]["tracked_qty"] == 2


def test_parity_drift_broker_extra():
    df = pd.DataFrame({"code": [_CODE_SPY_CALL], "qty": [3]})
    st = compute_position_parity_state(df, {}, _FABIO)
    assert st["parity_ok"] is False
    assert st["drifts"][0]["tracked_qty"] == 0


def test_parity_drift_qty_mismatch():
    df = pd.DataFrame({"code": [_CODE_SPY_CALL], "qty": [3]})
    tracked = {"SPY": {"code": _CODE_SPY_CALL, "remaining_qty": 2}}
    st = compute_position_parity_state(df, tracked, _FABIO)
    assert st["parity_ok"] is False
    d = st["drifts"][0]
    assert d["broker_qty"] == 3 and d["tracked_qty"] == 2


def test_parity_ignores_non_fabio_broker_symbols():
    code_other = "US.IWM260507P00200000"
    df = pd.DataFrame({"code": [code_other, _CODE_SPY_CALL], "qty": [10, 1]})
    tracked = {"SPY": {"code": _CODE_SPY_CALL, "remaining_qty": 1}}
    st = compute_position_parity_state(df, tracked, _FABIO)
    assert st["parity_ok"] is True
    assert code_other not in st["broker_codes"]


def test_parity_query_failure_state():
    tracked = {"SPY": {"code": _CODE_SPY_CALL, "remaining_qty": 2}}
    st = compute_position_parity_state(
        None,
        tracked,
        _FABIO,
        query_ok=False,
        query_ret=-1,
        query_error="position_list_query_nonzero_ret",
    )
    assert st["parity_ok"] is False
    assert st["query_ok"] is False
    assert st["tracked_codes"][_CODE_SPY_CALL] == 2


def test_tracked_skips_nonpositive_remaining():
    df = pd.DataFrame({"code": [_CODE_SPY_CALL], "qty": [2]})
    tracked = {"SPY": {"code": _CODE_SPY_CALL, "remaining_qty": 0}}
    st = compute_position_parity_state(df, tracked, _FABIO)
    assert st["parity_ok"] is False
    assert st["drifts"][0]["tracked_qty"] == 0


def test_maybe_alert_telegram_cooled_down_but_logs_each_time(monkeypatch):
    """Second drift notification within Telegram cooldown skips ops.alert but still logs."""

    clock = {"t": 1000.0}

    def _time_fn():
        return float(clock["t"])

    monkeypatch.setattr("fabio_live.bot.time.time", _time_fn)

    bot = ORBBot.__new__(ORBBot)
    log_calls = []
    alert_calls = []

    bot.ops = SimpleNamespace(
        log_alert=lambda tag, msg, sym: log_calls.append((tag, msg)),
        alert=lambda m: alert_calls.append(m),
    )
    bot._parity_alert_last_ts = 0.0

    drift = compute_position_parity_state(
        pd.DataFrame(columns=["code", "qty"]),
        {"QQQ": {"code": _CODE_SPY_CALL, "remaining_qty": 1}},
        _FABIO,
    )
    bot._maybe_alert_position_parity(drift)
    assert len(alert_calls) == 1 and len(log_calls) == 1

    bot._maybe_alert_position_parity(drift)
    assert len(alert_calls) == 1 and len(log_calls) == 2

    clock["t"] += float(OPS_ALERT_COOLDOWN_SEC) + 1.0
    bot._maybe_alert_position_parity(drift)
    assert len(alert_calls) == 2 and len(log_calls) == 3


def test_maybe_alert_skip_when_ok():
    bot = ORBBot.__new__(ORBBot)
    fired = []

    bot.ops = SimpleNamespace(
        log_alert=lambda *a: fired.append(a),
        alert=lambda m: fired.append(m),
    )

    bot._maybe_alert_position_parity(
        {
            "ok": True,
            "parity_ok": True,
            "query_ok": True,
            "drift_count": 0,
            "drifts": [],
        }
    )
    assert fired == []

