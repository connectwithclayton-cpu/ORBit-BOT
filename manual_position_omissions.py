"""
Operator-configured omissions: reconciled closes that intentionally must not appear in
canonical Sheets tabs or KPI/dashboard rollups while still existing in broker history.

Single source used by reconcile, dashboard aggregation, and full-stack audits.
"""

from __future__ import annotations

from typing import Any, List


MANUAL_OMITTED_POSITIONS: list[dict[str, Any]] = [
    {
        # Explicit operator omission — excluded from Sheets canonical + dashboard P&L.
        "date": "2026-05-07",
        "symbol": "NVDA",
        "direction": "CALL",
        "entry_hms": "09:59:33",
        "exit_hms": "10:23:09",
        "qty": 3988,
        # Dashboard field name (synonym for qty on close rows).
        "contracts": 3988,
    }
]


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        if v is None or v == "":
            return int(default)
        return int(float(v))
    except Exception:
        return int(default)


def operator_omission_fifo_mismatch_messages(recon_close_rows: List[List[Any]]) -> List[str]:
    """
    If operator omissions are configured, at least one FIFO close row should match;
    otherwise the omission spec is stale and nothing will be suppressed.
    """
    if not MANUAL_OMITTED_POSITIONS:
        return []
    if any(is_omitted_reconcile_close_row(r) for r in recon_close_rows):
        return []
    return [
        "MANUAL_OMITTED_POSITIONS is non-empty but no FIFO reconciled close row matched; "
        "update manual_position_omissions.py (date, entry_hms, exit_hms, qty/contracts) "
        "to a real FIFO row or clear the list."
    ]


def is_omitted_reconcile_close_row(row: List[Any]) -> bool:
    """
    Match reconciled close rows (FIFO output row shape).
    Row: [time, date, code, symbol, direction, qty, entry_time, entry_px,
          exit_time, exit_px, pnl, ret, note]
    """
    v = (list(row) + [""] * 13)[:13]
    date = str(v[1]).strip()
    symbol = str(v[3]).strip().upper()
    direction = str(v[4]).strip().upper()
    qty = _safe_int(v[5], 0)
    entry_hms = str(v[6])[11:19] if len(str(v[6])) >= 19 else str(v[6]).strip()
    exit_hms = str(v[8])[11:19] if len(str(v[8])) >= 19 else str(v[8]).strip()
    for p in MANUAL_OMITTED_POSITIONS:
        pq = _safe_int(p.get("qty", p.get("contracts", 0)), 0)
        if (
            date == str(p.get("date", "")).strip()
            and symbol == str(p.get("symbol", "")).strip().upper()
            and direction == str(p.get("direction", "")).strip().upper()
            and qty == pq
            and entry_hms == str(p.get("entry_hms", "")).strip()
            and exit_hms == str(p.get("exit_hms", "")).strip()
        ):
            return True
    return False


def is_omitted_dashboard_close_trade(t: Any) -> bool:
    """Match persisted dashboard / trade_data.json CLOSE rows."""
    if not isinstance(t, dict):
        return False
    date = str(t.get("date", "")).strip()
    symbol = str(t.get("symbol", "")).strip().upper()
    direction = str(t.get("direction", "")).strip().upper()
    entry_hms = str(t.get("entry_time", "")).strip()[:8]
    exit_hms = str(t.get("exit_time", "")).strip()[:8]
    try:
        contracts = int(float(t.get("contracts", 0) or 0))
    except (TypeError, ValueError):
        contracts = 0
    for p in MANUAL_OMITTED_POSITIONS:
        pq = _safe_int(p.get("contracts", p.get("qty", 0)), 0)
        if (
            date == str(p.get("date", "")).strip()
            and symbol == str(p.get("symbol", "")).strip().upper()
            and direction == str(p.get("direction", "")).strip().upper()
            and contracts == pq
            and entry_hms == str(p.get("entry_hms", "")).strip()
            and exit_hms == str(p.get("exit_hms", "")).strip()
        ):
            return True
    return False
