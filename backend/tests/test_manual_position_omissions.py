from __future__ import annotations

import manual_position_omissions as mpo
from manual_position_omissions import (
    MANUAL_OMITTED_POSITIONS,
    is_omitted_dashboard_close_trade,
    is_omitted_reconcile_close_row,
    operator_omission_fifo_mismatch_messages,
)


def test_omissions_list_non_empty_contract_with_operators_fixture():
    assert MANUAL_OMITTED_POSITIONS


def test_reconcile_row_match():
    row = [
        "2026-05-07 10:23:09",
        "2026-05-07",
        "US.NVDA260507C00150000",
        "NVDA",
        "CALL",
        3988,
        "2026-05-07 09:59:33",
        0.42,
        "2026-05-07 10:23:09",
        0.38,
        -15952.0,
        -10.5,
        "moomoo_paper_fifo",
    ]
    assert is_omitted_reconcile_close_row(row)


def test_dashboard_trade_match():
    t = {
        "date": "2026-05-07",
        "symbol": "NVDA",
        "direction": "CALL",
        "entry_time": "09:59:33",
        "exit_time": "10:23:09",
        "contracts": 3988,
        "ledger_leg": "CLOSE",
        "pnl": -15952.0,
    }
    assert is_omitted_dashboard_close_trade(t)


def test_non_match_different_qty():
    t = {
        "date": "2026-05-07",
        "symbol": "NVDA",
        "direction": "CALL",
        "entry_time": "09:59:33",
        "exit_time": "10:23:09",
        "contracts": 1,
        "ledger_leg": "CLOSE",
    }
    assert not is_omitted_dashboard_close_trade(t)


_NVDA_OMIT_ROW = [
    "2026-05-07 10:23:09",
    "2026-05-07",
    "US.NVDA260507C00150000",
    "NVDA",
    "CALL",
    3988,
    "2026-05-07 09:59:33",
    0.42,
    "2026-05-07 10:23:09",
    0.38,
    -15952.0,
    -10.5,
    "moomoo_paper_fifo",
]


def test_operator_omission_messages_empty_when_fifo_matches_configured_row():
    assert operator_omission_fifo_mismatch_messages([_NVDA_OMIT_ROW]) == []


def test_operator_omission_messages_when_row_does_not_match_config():
    bad = list(_NVDA_OMIT_ROW)
    bad[5] = 1  # qty
    msgs = operator_omission_fifo_mismatch_messages([bad])
    if MANUAL_OMITTED_POSITIONS:
        assert len(msgs) == 1
        assert "no FIFO reconciled close row matched" in msgs[0]


def test_operator_omission_messages_cleared_when_list_empty(monkeypatch):
    monkeypatch.setattr(mpo, "MANUAL_OMITTED_POSITIONS", [])
    assert operator_omission_fifo_mismatch_messages([]) == []
