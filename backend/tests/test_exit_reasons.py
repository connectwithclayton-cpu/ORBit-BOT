from __future__ import annotations

from exit_reasons import (
    CODE_EMA_CROSS,
    CODE_OTHER,
    CODE_RECONCILED_CLOSE,
    REASON_SOURCE_RECONCILE,
    REASON_SOURCE_STRATEGY,
    canonical_exit_reason,
)
from reconcile_moomoo_to_sheets import _canonical_to_dashboard_trades


def test_canonical_exit_reason_maps_strategy_reason():
    er = canonical_exit_reason("EMA 10/20 cross", source=REASON_SOURCE_STRATEGY)
    assert er.code == CODE_EMA_CROSS
    assert er.label == "EMA crossover"
    assert er.source == REASON_SOURCE_STRATEGY


def test_canonical_exit_reason_maps_reconcile_reason():
    er = canonical_exit_reason("Reconciled fill close", source=REASON_SOURCE_RECONCILE)
    assert er.code == CODE_RECONCILED_CLOSE
    assert er.source == REASON_SOURCE_RECONCILE


def test_canonical_exit_reason_unknown_falls_back_to_other():
    er = canonical_exit_reason("something new", source=REASON_SOURCE_STRATEGY)
    assert er.code == CODE_OTHER
    assert er.label == "Other"


def test_reconcile_rows_produce_reconcile_reason_fields():
    recon_rows = [
        [
            "2026-05-07 10:23:09",  # close time
            "2026-05-07",           # date
            "US.NVDA250509C00200000",
            "NVDA",
            "CALL",
            1,
            "2026-05-07 09:59:33",  # entry time
            1.23,
            "2026-05-07 10:23:09",  # exit time
            1.45,
            22.0,                   # pnl
            17.89,                  # return
            "moomoo_paper_fifo",
        ]
    ]
    trades, opens = _canonical_to_dashboard_trades(recon_rows, [])
    assert opens == []
    assert len(trades) == 1
    t = trades[0]
    assert t["exit_reason_code"] == CODE_RECONCILED_CLOSE
    assert t["reason_source"] == REASON_SOURCE_RECONCILE
    assert t["exit_reason"] == "Reconciled fill close"

