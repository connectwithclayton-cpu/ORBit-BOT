from __future__ import annotations

from reconcile_moomoo_to_sheets import (
    _annotate_reconciled_dashboard_trades_with_strategy_exits,
    _apply_sheets_down_exit_reason_fallback,
    _parse_strategy_exit_rows_from_trades_sheet_rows,
)


def test_parse_strategy_exit_rows_from_trades_sheet_rows_filters_strategy_only():
    rows = [
        # date, symbol, dir, entry_time, entry_px, strike, expiry, contracts, exit_time, exit_px,
        # pnl, ret, exit_reason, vix, oratr, cap, trend, vixregime, day, notes,
        # exit_reason_code, reason_source, reason_detail
        [
            "2026-05-08",
            "SPY",
            "CALL",
            "09:45:00",
            "1.0",
            "",
            "",
            "2",
            "10:15:00",
            "1.2",
            "40",
            "20",
            "EMA crossover",
            "24.6",
            "",
            "",
            "",
            "AGGRESSIVE(20-28)",
            "",
            "",
            "EMA_CROSS",
            "strategy",
            "",
        ],
        [
            "2026-05-08",
            "SPY",
            "CALL",
            "09:45:00",
            "1.0",
            "",
            "",
            "2",
            "10:15:00",
            "1.2",
            "40",
            "20",
            "Reconciled fill close",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "RECONCILED_CLOSE",
            "reconcile",
            "",
        ],
    ]
    out = _parse_strategy_exit_rows_from_trades_sheet_rows(rows, "2026-05-08")
    assert len(out) == 1
    assert out[0]["exit_reason_code"] == "EMA_CROSS"
    assert out[0]["reason_source"] == "strategy"
    assert out[0]["vix"] == 24.6
    assert out[0]["vix_regime"] == "AGGRESSIVE(20-28)"


def test_annotate_reconciled_dashboard_trades_overrides_exit_reason_fields():
    dashboard_trades = [
        {
            "date": "2026-05-08",
            "symbol": "SPY",
            "direction": "CALL",
            "entry_time": "09:45:00",
            "exit_time": "10:15:00",
            "contracts": 2,
            "ledger_leg": "CLOSE",
            "exit_reason": "Reconciled fill close",
            "exit_reason_code": "RECONCILED_CLOSE",
            "reason_source": "reconcile",
        }
    ]
    strategy_exits = [
        {
            "date": "2026-05-08",
            "symbol": "SPY",
            "direction": "CALL",
            "contracts": 2,
            "entry_hms": "09:45:00",
            "exit_hms": "10:15:00",
            "exit_reason": "EMA crossover",
            "exit_reason_code": "EMA_CROSS",
            "reason_source": "strategy",
            "vix": 24.6,
            "vix_regime": "AGGRESSIVE(20-28)",
        }
    ]
    n = _annotate_reconciled_dashboard_trades_with_strategy_exits(
        dashboard_trades, strategy_exits
    )
    assert n == 1
    t = dashboard_trades[0]
    assert t["exit_reason"] == "EMA crossover"
    assert t["exit_reason_code"] == "EMA_CROSS"
    assert t["reason_source"] == "strategy"
    assert t["fill_source"] == "reconcile"
    assert t["vix"] == 24.6
    assert t["vix_regime"] == "AGGRESSIVE(20-28)"


def test_sheets_down_fallback_labels_eod_window_only():
    dashboard_trades = [
        {
            "date": "2026-05-08",
            "symbol": "SPY",
            "direction": "CALL",
            "entry_time": "10:00:00",
            "exit_time": "15:45:00",
            "contracts": 1,
            "ledger_leg": "CLOSE",
            "exit_reason": "Reconciled fill close",
            "exit_reason_code": "RECONCILED_CLOSE",
            "reason_source": "reconcile",
        },
        {
            "date": "2026-05-08",
            "symbol": "QQQ",
            "direction": "CALL",
            "entry_time": "10:00:00",
            "exit_time": "11:00:00",
            "contracts": 1,
            "ledger_leg": "CLOSE",
            "exit_reason": "Reconciled fill close",
            "exit_reason_code": "RECONCILED_CLOSE",
            "reason_source": "reconcile",
        },
    ]
    n = _apply_sheets_down_exit_reason_fallback(dashboard_trades)
    assert n == 1
    assert dashboard_trades[0]["exit_reason_code"] == "EOD_CLOSE"
    assert dashboard_trades[0]["reason_source"] == "strategy"
    assert dashboard_trades[0]["fill_source"] == "reconcile"
    # Non-EOD remains unchanged.
    assert dashboard_trades[1]["exit_reason_code"] == "RECONCILED_CLOSE"

