#!/usr/bin/env python3
"""
Full reconciliation audit — Moomoo SIMULATE vs Sheets canonical tabs and dashboard.

Expected artifacts match `reconcile_moomoo_to_sheets` (FIFO + operator omissions in
`manual_position_omissions.py`). Broker history still lists fills for omitted
round-trips; they must NOT appear on Broker Fills (effective set), Reconciled
Trades, or reconciled-derived dashboard closes.

Exit: 0 pass, 1 drift, 2 error/config.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _load_audit_helpers():
    scripts = _ROOT / "scripts" / "audit_moomoo_sync.py"
    name = "_fabio_audit_helpers"
    spec = importlib.util.spec_from_file_location(name, scripts)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {scripts}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


from dashboard_writer import (  # noqa: E402
    DATA_FILE as DASH_DATA_FILE,
    aggregate_closed_positions,
    dashboard_row_derived_from_moomoo_sync,
)
from manual_position_omissions import (  # noqa: E402
    MANUAL_OMITTED_POSITIONS,
    is_omitted_dashboard_close_trade,
    operator_omission_fifo_mismatch_messages,
)
from reconcile_moomoo_to_sheets import (  # noqa: E402
    _canonical_to_dashboard_trades,
    _fetch_all_paper_fills,
    _fetch_broker_open_inventory,
    _is_moomoo_record_manually_omitted,
    _is_manually_omitted_recon_row,
    _omitted_position_refs_from_recon_rows,
    _reconcile_fifo,
    _to_broker_fill_rows,
)
from sheets_logger import (  # noqa: E402
    GSPREAD_AVAILABLE,
    SheetsLogger,
    TAB_BROKER_FILLS,
    TAB_OPEN_INVENTORY,
    TAB_RECON_TRADES,
)


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return float(default)
        return float(v)
    except Exception:
        return float(default)


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        if v is None or v == "":
            return int(default)
        return int(float(v))
    except Exception:
        return int(default)


def _hms(t: Any) -> str:
    s = str(t or "").strip()
    if len(s) >= 19 and s[4] == "-" and s[7] == "-" and s[10] == " ":
        return s[11:19]
    return s[:8]


def _sheet_rows(logger_tabs: dict, tab: str) -> list[list[str]]:
    ws = logger_tabs["_tabs"].get(tab)
    if ws is None:
        return []
    vals = ws.get_all_values()
    return vals[1:] if len(vals) > 1 else []


def _option_broker_fill_ids_from_sheet_rows(rows: list[list[str]], aud) -> set[str]:
    """All option instrument fill_ids (BUY and SELL) on Broker Fills tab."""
    out: set[str] = set()
    for row in rows:
        r = (list(row) + [""] * 12)[:12]
        fid = str(r[0]).strip()
        code = str(r[3]).strip()
        qty = _safe_int(r[7], 0)
        if not fid or qty <= 0:
            continue
        if not aud._is_option_code(code):
            continue
        out.add(fid)
    return out


def _close_position_key(t: dict) -> tuple:
    return (
        str(t.get("date", "")).strip(),
        str(t.get("symbol", "")).strip().upper(),
        str(t.get("direction", "")).strip().upper(),
        _hms(t.get("entry_time", "")),
        _hms(t.get("exit_time", "")),
        _safe_int(t.get("contracts", 0), 0),
        round(_safe_float(t.get("pnl", 0.0), 0.0), 2),
    )


def _day_net_from_closed(trades: list[dict]) -> dict[str, float]:
    by_day: dict[str, float] = defaultdict(float)
    for p in aggregate_closed_positions(trades):
        d = str(p.get("date", "")).strip()
        if not d:
            continue
        by_day[d] += round(_safe_float(p.get("pnl", 0.0), 0.0), 2)
    return {k: round(v, 2) for k, v in by_day.items()}


def _fifo_close_count_by_date(recon_row_lists: list[list]) -> dict[str, int]:
    """Count FIFO reconciled close rows per session date (column 1)."""
    c: dict[str, int] = defaultdict(int)
    for row in recon_row_lists:
        r = (list(row) + [""] * 13)[:13]
        d = str(r[1]).strip()
        if d:
            c[d] += 1
    return dict(sorted(c.items()))


def _dashboard_close_count_by_date(trades_like: list[dict]) -> dict[str, int]:
    c: dict[str, int] = defaultdict(int)
    for t in trades_like:
        if not isinstance(t, dict):
            continue
        d = str(t.get("date", "")).strip()
        if d:
            c[d] += 1
    return dict(sorted(c.items()))


def _recon_row_tuple(r: dict) -> tuple:
    return (
        str(r.get("close_time", "")).strip(),
        str(r.get("date", "")).strip(),
        str(r.get("code", "")).strip(),
        _safe_int(r.get("qty", 0), 0),
        round(_safe_float(r.get("pnl", 0.0), 0.0), 2),
        str(r.get("source", "")).strip(),
    )


def main() -> int:
    load_dotenv(_ROOT / ".env")
    aud = _load_audit_helpers()

    if not GSPREAD_AVAILABLE:
        print("ERROR: gspread unavailable")
        return 2

    print("Fetching Moomoo SIMULATE fills (full history)...")
    moomoo_records = _fetch_all_paper_fills()
    print(f"  broker records: {len(moomoo_records)}")

    recon_all, fifo_open_rows = _reconcile_fifo(moomoo_records)
    omitted_refs = _omitted_position_refs_from_recon_rows(recon_all)
    omitted_recon_rows = [r for r in recon_all if _is_manually_omitted_recon_row(r)]
    moomoo_effective = [
        rec for rec in moomoo_records if not _is_moomoo_record_manually_omitted(rec, omitted_refs)
    ]
    recon_fifo_filtered = [r for r in recon_all if not _is_manually_omitted_recon_row(r)]

    expected_broker_ids = {
        str(r[0]).strip() for r in _to_broker_fill_rows(moomoo_effective) if str(r[0]).strip()
    }

    omitted_fill_ids_should_stay_out = {
        str(rec["fill_id"]).strip()
        for rec in moomoo_records
        if _is_moomoo_record_manually_omitted(rec, omitted_refs)
        and aud._is_option_code(rec.get("code", ""))
    }

    broker_open = _fetch_broker_open_inventory()
    open_codes = [c for c, q in broker_open.items() if _safe_int(q, 0) > 0 and aud._is_option_code(c)]

    print("Connecting to Google Sheets...")
    logger = SheetsLogger()
    if not logger.is_connected():
        print("ERROR: Sheets logger not connected")
        return 2
    tabs = {"_tabs": logger._tabs}

    sheet_broker_rows = _sheet_rows(tabs, TAB_BROKER_FILLS)
    sheet_broker_ids = _option_broker_fill_ids_from_sheet_rows(sheet_broker_rows, aud)
    sheet_recon_norm = aud._normalize_recon_rows(_sheet_rows(tabs, TAB_RECON_TRADES))
    open_sheet = aud._normalize_open_inventory_rows(_sheet_rows(tabs, TAB_OPEN_INVENTORY))

    moomoo_open: dict[str, int] = {}
    for code, q in broker_open.items():
        if not aud._is_option_code(code):
            continue
        qq = _safe_int(q, 0)
        if qq > 0:
            moomoo_open[code] = moomoo_open.get(code, 0) + qq

    fifo_open_norm = aud._normalize_open_inventory_rows(fifo_open_rows)

    exp_trades, _ = _canonical_to_dashboard_trades(recon_fifo_filtered, fifo_open_rows)
    exp_closed_keys = [_close_position_key(t) for t in exp_trades if isinstance(t, dict)]

    dash_path = Path(DASH_DATA_FILE)
    dash_raw = {}
    if dash_path.exists():
        try:
            dash_raw = json.loads(dash_path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"ERROR reading {dash_path}: {e}")
            return 2

    trades = dash_raw.get("trades") if isinstance(dash_raw.get("trades"), list) else []

    dash_moomoo_closes = []
    for t in trades:
        if not isinstance(t, dict):
            continue
        if str(t.get("ledger_leg", "")).upper() != "CLOSE":
            continue
        if not dashboard_row_derived_from_moomoo_sync(t):
            continue
        dash_moomoo_closes.append(t)

    dash_keys = [_close_position_key(t) for t in dash_moomoo_closes]

    exp_fifo_tuples = sorted(
        _recon_row_tuple(r) for r in aud._normalize_recon_rows(recon_fifo_filtered)
    )
    sheet_recon_tuples = sorted(_recon_row_tuple(r) for r in sheet_recon_norm)

    # reconcile replaces recon tab with fifo rows excluding omitted — compare sheet to fifo-normalized expectation
    issues: list[str] = []

    missing_broker = sorted(expected_broker_ids - sheet_broker_ids)
    extra_broker = sorted(sheet_broker_ids - expected_broker_ids)
    if missing_broker:
        issues.append(f"broker_fill_ids missing in sheet ({len(missing_broker)})")
    if extra_broker:
        issues.append(f"broker_fill_ids on sheet but not in expected Moomoo effective set ({len(extra_broker)})")

    leaked_omitted = sorted(omitted_fill_ids_should_stay_out & sheet_broker_ids)
    if leaked_omitted:
        issues.append(f"omitted-position fills leaked to Broker Fills tab ({len(leaked_omitted)})")

    inv_match = moomoo_open == open_sheet
    if not inv_match:
        issues.append(
            f"open inventory mismatch moomoo={moomoo_open} sheet={open_sheet} "
            f"(fifo_open={fifo_open_norm})"
        )

    if Counter(exp_fifo_tuples) != Counter(sheet_recon_tuples):
        issues.append(
            "reconciled trades tab mismatch vs FIFO expectation "
            f"(expected_rows={len(exp_fifo_tuples)} sheet_rows={len(sheet_recon_tuples)})"
        )

    # Operator omission spec vs FIFO (shared check with reconcile)
    if MANUAL_OMITTED_POSITIONS:
        for spec in MANUAL_OMITTED_POSITIONS:
            print(f"  omission rule: {spec.get('date')} {spec.get('symbol')} {spec.get('direction')}")
        issues.extend(operator_omission_fifo_mismatch_messages(recon_all))
        if omitted_recon_rows and not omitted_fill_ids_should_stay_out:
            issues.append(
                "omitted recon row(s) present but suppressed fill_ids empty — check _omitted_position_refs_from_recon_rows"
            )

    leaked_omitted_dash = [t for t in dash_moomoo_closes if is_omitted_dashboard_close_trade(t)]
    if leaked_omitted_dash:
        issues.append(
            f"omitted round-trip still present in dashboard ({len(leaked_omitted_dash)} row(s))"
        )

    exp_day = _day_net_from_closed(exp_trades)
    dash_day = _day_net_from_closed(dash_moomoo_closes)
    day_keys = sorted(set(exp_day.keys()) | set(dash_day.keys()))
    pnl_drift = {d: round(abs(exp_day.get(d, 0.0) - dash_day.get(d, 0.0)), 2) for d in day_keys}
    bad_days = [d for d, x in pnl_drift.items() if x > 0.02]
    if bad_days:
        issues.append(f"dashboard vs expected daily P&L mismatch days: {bad_days} deltas={ {d: pnl_drift[d] for d in bad_days} }")

    if Counter(exp_closed_keys) != Counter(dash_keys):
        issues.append(
            f"dashboard reconciled-close keys mismatch (expected {len(exp_closed_keys)} vs {len(dash_keys)})"
        )
        only_exp = sorted((Counter(exp_closed_keys) - Counter(dash_keys)).elements())
        only_dash = sorted((Counter(dash_keys) - Counter(exp_closed_keys)).elements())
        if only_exp[:5]:
            print("  sample only-in-expected:", only_exp[:5])
        if only_dash[:5]:
            print("  sample only-in-dashboard:", only_dash[:5])

    fifo_by_date = _fifo_close_count_by_date(recon_fifo_filtered)
    dash_by_date = _dashboard_close_count_by_date(dash_moomoo_closes)
    sheet_recon_by_date: dict[str, int] = defaultdict(int)
    for r in sheet_recon_norm:
        if isinstance(r, dict):
            d = str(r.get("date", "")).strip()
            if d:
                sheet_recon_by_date[d] += 1
    sheet_recon_by_date = dict(sorted(sheet_recon_by_date.items()))
    date_keys = sorted(set(fifo_by_date) | set(dash_by_date) | set(sheet_recon_by_date))

    print()
    print("=== Per-date reconciled CLOSE row counts ===")
    print("(FIFO expected | dashboard store | Sheets Reconciled Trades tab)")
    for d in date_keys:
        print(
            f"  {d}: fifo={fifo_by_date.get(d, 0)} | "
            f"dash={dash_by_date.get(d, 0)} | sheet={sheet_recon_by_date.get(d, 0)}"
        )
    print(
        "  Note: multiple rows per calendar day per symbol often means partial exits / scaling "
        "(separate FIFO segments), not missing broker fills."
    )

    print()
    print("=== Audit summary ===")
    print(f"Moomoo option open codes: {len(open_codes)}")
    print(f"Expected broker option fill_ids: {len(expected_broker_ids)} | sheet: {len(sheet_broker_ids)}")
    print(f"Reconciled closes (FIFO, omissions applied): {len(recon_fifo_filtered)}")
    print(f"Dashboard moomoo-derived CLOSE rows: {len(dash_moomoo_closes)}")
    print(f"Open inventory match (Moomoo vs sheet): {inv_match}")

    if issues:
        print("\nFAIL — issues:")
        for i in issues:
            print(f"  - {i}")
        if not sheet_broker_ids and expected_broker_ids:
            print(
                "\nHint: canonical tabs look empty but Moomoo expects broker rows. "
                "Run `python3 reconcile_moomoo_to_sheets.py` (watch exit code; 0=ok). "
                "Check console for `[SheetsLogger] replace_tab_rows` traceback or "
                "`CANONICAL_PUBLISH` / `RECONCILE_MISMATCH` alerts."
            )
        return 1

    print("\nPASS — Sheets and dashboard match Moomoo-derived expectations (omissions honored).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
