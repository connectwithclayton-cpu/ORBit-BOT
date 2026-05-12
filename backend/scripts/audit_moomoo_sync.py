#!/usr/bin/env python3
"""
Read-only sync audit for Fabio bot data surfaces.

Authoritative source: Moomoo broker records.

This script compares:
1) Moomoo closed option SELL fills
2) Google Sheets canonical tabs (Broker Fills, Reconciled Trades, Open Inventory)
3) Dashboard data store (backend/trade_data.json daily rollups + trade rows)

Output:
- Append-only JSONL audit log (default: ./audit_sync.jsonl)
- Optional alerting (Telegram + Sheets Alerts tab) with consecutive-failure gating

Exit codes:
- 0: pass
- 1: audit drift/failure
- 2: runtime/config error
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

import moomoo as ft
from moomoo import OpenSecTradeContext, RET_OK, SecurityFirm, TrdEnv, TrdMarket

_BACKEND = Path(__file__).resolve().parents[1]
_FABIO_ROOT = _BACKEND.parent
for _p in (_BACKEND, _FABIO_ROOT / "frontend"):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)

from dashboard_writer import DATA_FILE as DASH_DATA_FILE
from sheets_logger import (
    GSPREAD_AVAILABLE,
    SheetsLogger,
    TAB_BROKER_FILLS,
    TAB_OPEN_INVENTORY,
    TAB_RECON_TRADES,
)

try:
    import telegram_bot as tg
except Exception:
    tg = None

_OPTION_CODE_CORE_RE = re.compile(r"([A-Z]+)\d{6}([CP])\d+")


@dataclass
class SeverityResult:
    severity: str
    reason: str


def _now_iso_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


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


def _is_option_code(code: str) -> bool:
    raw = str(code or "").split(".")[-1]
    return bool(_OPTION_CODE_CORE_RE.match(raw))


def _moomoo_fill_id(updated_time: str, code: str, side: str, qty: int, price: float) -> str:
    ts = str(updated_time or "")[:19]
    return f"{ts}|{code}|{side}|{qty}|{price:.4f}"


def _parse_dt_utc(ts: str) -> dt.datetime | None:
    s = str(ts or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            d = dt.datetime.strptime(s[:19], fmt)
            return d.replace(tzinfo=dt.timezone.utc)
        except Exception:
            continue
    return None


def _read_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json_file(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, default=str) + "\n")


def _fetch_moomoo_closed_option_sells(lookback_minutes: int) -> list[dict]:
    host = os.getenv("MOOMOO_HOST", "127.0.0.1")
    port = int(os.getenv("MOOMOO_PORT", "11111"))
    end_local = dt.datetime.now()
    start_local = end_local - dt.timedelta(minutes=max(lookback_minutes, 1))
    start_dt = start_local.strftime("%Y-%m-%d %H:%M:%S")
    end_dt = end_local.strftime("%Y-%m-%d %H:%M:%S")

    ctx = OpenSecTradeContext(
        filter_trdmarket=TrdMarket.US,
        host=host,
        port=port,
        security_firm=SecurityFirm.FUTUINC,
    )
    try:
        ret, hist = ctx.history_order_list_query(
            status_filter_list=[ft.OrderStatus.FILLED_ALL, ft.OrderStatus.FILLED_PART],
            start=start_dt,
            end=end_dt,
            trd_env=TrdEnv.SIMULATE,
        )
        if ret != RET_OK:
            raise RuntimeError(f"history_order_list_query failed: {hist}")
        if hist is None or hist.empty:
            return []
        out: list[dict] = []
        for _, r in hist.iterrows():
            code = str(r.get("code", "")).strip()
            side = str(r.get("trd_side", "")).strip().upper()
            qty = _safe_int(r.get("dealt_qty", r.get("qty", 0)), 0)
            px = _safe_float(r.get("dealt_avg_price", 0.0), 0.0)
            if qty <= 0:
                continue
            if "SELL" not in side:
                continue
            if not _is_option_code(code):
                continue
            ts = str(r.get("updated_time", r.get("create_time", "")))[:19]
            out.append(
                {
                    "fill_id": _moomoo_fill_id(ts, code, side, qty, px),
                    "time": ts,
                    "date": ts[:10],
                    "code": code,
                    "side": side,
                    "qty": qty,
                    "price": round(px, 4),
                    "realized_pnl": round(
                        _safe_float(r.get("realized_pl", r.get("realized_pnl", 0.0))), 2
                    ),
                }
            )
        out.sort(key=lambda x: x["time"])
        return out
    finally:
        ctx.close()


def _fetch_moomoo_open_inventory() -> dict[str, int]:
    host = os.getenv("MOOMOO_HOST", "127.0.0.1")
    port = int(os.getenv("MOOMOO_PORT", "11111"))
    ctx = OpenSecTradeContext(
        filter_trdmarket=TrdMarket.US,
        host=host,
        port=port,
        security_firm=SecurityFirm.FUTUINC,
    )
    try:
        ret, pos = ctx.position_list_query(trd_env=TrdEnv.SIMULATE)
        if ret != RET_OK or pos is None or pos.empty:
            return {}
        out: dict[str, int] = {}
        for _, r in pos.iterrows():
            code = str(r.get("code", "")).strip()
            qty = _safe_int(r.get("qty", 0), 0)
            if qty <= 0:
                continue
            if not _is_option_code(code):
                continue
            out[code] = out.get(code, 0) + qty
        return out
    finally:
        ctx.close()


def _load_sheet_snapshot() -> dict[str, Any]:
    if not GSPREAD_AVAILABLE:
        raise RuntimeError("gspread/google-auth unavailable")
    logger = SheetsLogger()
    if not logger.is_connected():
        raise RuntimeError("SheetsLogger not connected")
    tabs = logger._tabs  # existing connected worksheet handles

    def rows(tab: str) -> list[list[str]]:
        ws = tabs.get(tab)
        if ws is None:
            return []
        vals = ws.get_all_values()
        return vals[1:] if len(vals) > 1 else []

    broker_rows = rows(TAB_BROKER_FILLS)
    recon_rows = rows(TAB_RECON_TRADES)
    open_rows = rows(TAB_OPEN_INVENTORY)
    return {
        "logger": logger,
        "broker_rows": broker_rows,
        "recon_rows": recon_rows,
        "open_rows": open_rows,
    }


def _normalize_broker_fill_rows(rows: list[list[str]]) -> list[dict]:
    out: list[dict] = []
    for row in rows:
        r = (list(row) + [""] * 12)[:12]
        fill_id = str(r[0]).strip()
        ts = str(r[1]).strip()
        code = str(r[3]).strip()
        side = str(r[6]).strip().upper()
        qty = _safe_int(r[7], 0)
        price = _safe_float(r[8], 0.0)
        if not fill_id or qty <= 0:
            continue
        if "SELL" not in side:
            continue
        if not _is_option_code(code):
            continue
        out.append(
            {
                "fill_id": fill_id,
                "time": ts,
                "date": str(r[2]).strip() or ts[:10],
                "code": code,
                "side": side,
                "qty": qty,
                "price": round(price, 4),
                "realized_pnl": round(_safe_float(r[10], 0.0), 2),
            }
        )
    out.sort(key=lambda x: x["time"])
    return out


def _normalize_recon_rows(rows: list[list[str]]) -> list[dict]:
    out: list[dict] = []
    for row in rows:
        r = (list(row) + [""] * 13)[:13]
        code = str(r[2]).strip()
        date = str(r[1]).strip()
        qty = _safe_int(r[5], 0)
        pnl = _safe_float(r[10], 0.0)
        if not code or qty <= 0:
            continue
        if not _is_option_code(code):
            continue
        out.append(
            {
                "close_time": str(r[0]).strip(),
                "date": date,
                "code": code,
                "qty": qty,
                "pnl": round(pnl, 2),
                "source": str(r[12]).strip(),
            }
        )
    out.sort(key=lambda x: x["close_time"])
    return out


def _normalize_open_inventory_rows(rows: list[list[str]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        r = (list(row) + [""] * 10)[:10]
        code = str(r[2]).strip()
        qty = _safe_int(r[5], 0)
        if not code or qty <= 0:
            continue
        if not _is_option_code(code):
            continue
        out[code] = out.get(code, 0) + qty
    return out


def _load_dashboard_snapshot(path: Path) -> dict[str, Any]:
    payload = _read_json_file(path, {"trades": [], "daily": [], "open_positions": []})
    trades = payload.get("trades", []) if isinstance(payload, dict) else []
    daily = payload.get("daily", []) if isinstance(payload, dict) else []
    backfill_session_rows = 0
    for t in trades if isinstance(trades, list) else []:
        if not isinstance(t, dict):
            continue
        reason = str(t.get("exit_reason", "")).strip().lower()
        notes = str(t.get("notes", "")).strip().lower()
        included = t.get("include_in_session_pnl", True) is not False
        if included and (
            reason == "moomoo fill backfill" or "source=moomoo_paper" in notes
        ):
            backfill_session_rows += 1
    return {
        "trades": trades if isinstance(trades, list) else [],
        "daily": daily if isinstance(daily, list) else [],
        "backfill_session_rows": backfill_session_rows,
    }


def _per_day_pnl_from_recon(recon_rows: list[dict]) -> dict[str, float]:
    out: dict[str, float] = defaultdict(float)
    for r in recon_rows:
        out[str(r["date"])] += float(r["pnl"])
    return {k: round(v, 2) for k, v in out.items()}


def _per_day_pnl_from_daily(daily_rows: list[dict]) -> dict[str, float]:
    out: dict[str, float] = {}
    for d in daily_rows:
        if not isinstance(d, dict):
            continue
        day = str(d.get("date", "")).strip()
        if not day:
            continue
        out[day] = round(_safe_float(d.get("net_pnl", 0.0), 0.0), 2)
    return out


def _severity_from_failures(
    failures: list[str], inventory_ok: bool, eod_mode: bool, consecutive_failures: int
) -> SeverityResult:
    if not failures:
        return SeverityResult("INFO", "audit_pass")
    critical_keys = (
        "missing_broker_fill_ids",
        "inventory_mismatch",
    )
    hard = any(any(k in f for k in critical_keys) for f in failures)
    if eod_mode and failures:
        hard = True
    if hard and consecutive_failures >= 2:
        return SeverityResult("CRITICAL", "drift_confirmed")
    if hard:
        return SeverityResult("WARNING", "first_hard_drift")
    if not inventory_ok:
        return SeverityResult("WARNING", "inventory_warning")
    return SeverityResult("WARNING", "soft_drift")


def _market_hours_et(now_et: dt.datetime) -> bool:
    # Lightweight heuristic for intraday classification inside this script only.
    # Launchd wrappers use fabio_live.calendar_gate + XNYS for holidays / session bounds.
    if now_et.weekday() >= 5:
        return False
    return (now_et.hour > 9 or (now_et.hour == 9 and now_et.minute >= 30)) and (
        now_et.hour < 16 or (now_et.hour == 16 and now_et.minute <= 10)
    )


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Moomoo-authoritative sync audit")
    p.add_argument("--lookback-min", type=int, default=180)
    p.add_argument("--eod", action="store_true", help="Mark this run as post-close audit")
    p.add_argument("--max-runtime-sec", type=float, default=10.0)
    p.add_argument("--pnl-tolerance", type=float, default=0.01)
    p.add_argument("--jsonl", default="audit_sync.jsonl")
    p.add_argument("--state-file", default="audit_sync_state.json")
    p.add_argument("--dashboard-data", default=DASH_DATA_FILE)
    p.add_argument("--alert-after-failures", type=int, default=2)
    p.add_argument("--enable-telegram-alerts", action="store_true")
    p.add_argument("--log-alerts-to-sheets", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--jitter-max-sec", type=float, default=0.0)
    p.add_argument(
        "--print-option-sell-realized-by-date",
        action="store_true",
        help="Sum realized_pl from option SELL fills in the lookback window, grouped by ET date "
        "(for broker vs reconcile sanity checks). Skips audit JSON/market-hours gate.",
    )
    return p


def main() -> int:
    from fabio_bot_paths import fabio_bot_root

    load_dotenv(fabio_bot_root() / ".env")
    args = _build_parser().parse_args()
    t0 = time.monotonic()

    if args.print_option_sell_realized_by_date:
        fills = _fetch_moomoo_closed_option_sells(max(int(args.lookback_min), 1))
        by_date: dict[str, float] = {}
        for x in fills:
            d = str(x.get("date") or "")[:10]
            if not d:
                continue
            by_date[d] = by_date.get(d, 0.0) + float(x.get("realized_pnl") or 0.0)
        print(
            f"Option SELL fills in last {max(int(args.lookback_min), 1)} minutes: {len(fills)}"
        )
        for d in sorted(by_date.keys()):
            print(f"  {d}  sum(realized_pl) = {round(by_date[d], 2)}")
        return 0

    if args.jitter_max_sec > 0:
        time.sleep(random.uniform(0.0, float(args.jitter_max_sec)))

    now_et = dt.datetime.now(ZoneInfo("America/New_York"))
    state_path = Path(args.state_file)
    jsonl_path = Path(args.jsonl)
    dashboard_path = Path(args.dashboard_data)
    state = _read_json_file(state_path, {"consecutive_failures": 0, "last_status": "UNKNOWN"})
    consecutive_failures = int(state.get("consecutive_failures", 0))

    event: dict[str, Any] = {
        "ts": _now_iso_utc(),
        "event": "sync_audit",
        "config": {
            "lookback_min": args.lookback_min,
            "eod": bool(args.eod),
            "pnl_tolerance": float(args.pnl_tolerance),
            "dry_run": bool(args.dry_run),
        },
        "checks": {},
        "drift": {},
        "status": "UNKNOWN",
        "severity": "INFO",
    }

    try:
        if not args.eod and not _market_hours_et(now_et):
            event["status"] = "SKIP"
            event["severity"] = "INFO"
            event["reason"] = "outside_market_window"
            event["latency_ms"] = round((time.monotonic() - t0) * 1000, 1)
            _append_jsonl(jsonl_path, event)
            _write_json_file(
                state_path,
                {
                    "consecutive_failures": consecutive_failures,
                    "last_status": "SKIP",
                    "last_severity": "INFO",
                    "last_ts": event["ts"],
                },
            )
            return 0

        moomoo_closed = _fetch_moomoo_closed_option_sells(args.lookback_min)
        moomoo_open = _fetch_moomoo_open_inventory()
        sheets = _load_sheet_snapshot()
        broker_fills = _normalize_broker_fill_rows(sheets["broker_rows"])
        recon_rows = _normalize_recon_rows(sheets["recon_rows"])
        open_inventory = _normalize_open_inventory_rows(sheets["open_rows"])
        dashboard = _load_dashboard_snapshot(Path(dashboard_path))

        moomoo_ids = {x["fill_id"] for x in moomoo_closed}
        sheet_ids = {x["fill_id"] for x in broker_fills}
        missing_in_sheets = sorted(moomoo_ids - sheet_ids)
        duplicate_sheet_ids = sorted(
            [k for k, v in Counter([x["fill_id"] for x in broker_fills]).items() if v > 1]
        )
        inventory_match = moomoo_open == open_inventory

        recon_day = _per_day_pnl_from_recon(recon_rows)
        dash_day = _per_day_pnl_from_daily(dashboard["daily"])
        day_union = sorted(set(recon_day.keys()) | set(dash_day.keys()))
        day_deltas = {
            d: round(abs(recon_day.get(d, 0.0) - dash_day.get(d, 0.0)), 2) for d in day_union
        }
        pnl_mismatch_days = sorted([d for d, delta in day_deltas.items() if delta > args.pnl_tolerance])

        failures: list[str] = []
        if missing_in_sheets:
            failures.append(f"missing_broker_fill_ids:{len(missing_in_sheets)}")
        if duplicate_sheet_ids:
            failures.append(f"duplicate_broker_fill_ids:{len(duplicate_sheet_ids)}")
        if not inventory_match:
            failures.append("inventory_mismatch")
        if pnl_mismatch_days:
            failures.append(f"dashboard_pnl_mismatch_days:{len(pnl_mismatch_days)}")
        if dashboard["backfill_session_rows"] > 0:
            failures.append(
                f"classification_integrity_backfill_in_session:{dashboard['backfill_session_rows']}"
            )

        event["checks"] = {
            "moomoo_closed_option_sell_count": len(moomoo_closed),
            "sheet_broker_fill_sell_count": len(broker_fills),
            "sheet_reconciled_trade_count": len(recon_rows),
            "sheet_open_inventory_codes": len(open_inventory),
            "moomoo_open_inventory_codes": len(moomoo_open),
            "inventory_match": inventory_match,
            "dashboard_backfill_session_rows": int(dashboard["backfill_session_rows"]),
        }
        event["drift"] = {
            "missing_broker_fill_ids": missing_in_sheets[:50],
            "missing_broker_fill_ids_count": len(missing_in_sheets),
            "duplicate_broker_fill_ids": duplicate_sheet_ids[:50],
            "duplicate_broker_fill_ids_count": len(duplicate_sheet_ids),
            "inventory_moomoo": moomoo_open,
            "inventory_sheet": open_inventory,
            "pnl_deltas_by_day": day_deltas,
            "pnl_mismatch_days": pnl_mismatch_days,
            "failures": failures,
        }

        if failures:
            consecutive_failures += 1
            event["status"] = "FAIL"
        else:
            consecutive_failures = 0
            event["status"] = "PASS"

        sev = _severity_from_failures(failures, inventory_match, bool(args.eod), consecutive_failures)
        event["severity"] = sev.severity
        event["severity_reason"] = sev.reason
        event["consecutive_failures"] = consecutive_failures

        elapsed = round((time.monotonic() - t0) * 1000, 1)
        event["latency_ms"] = elapsed
        if elapsed > float(args.max_runtime_sec) * 1000:
            event["runtime_warning"] = f"latency_ms_exceeded:{elapsed}"
            if event["status"] == "PASS":
                event["severity"] = "WARNING"
                event["severity_reason"] = "runtime_budget_exceeded"

        _append_jsonl(jsonl_path, event)
        _write_json_file(
            state_path,
            {
                "consecutive_failures": consecutive_failures,
                "last_status": event["status"],
                "last_severity": event["severity"],
                "last_ts": event["ts"],
            },
        )

        should_alert = (
            event["status"] == "FAIL"
            and consecutive_failures >= int(args.alert_after_failures)
            and event["severity"] in ("WARNING", "CRITICAL")
            and not args.dry_run
        )
        if should_alert:
            msg = (
                "⚠️ <b>SYNC AUDIT DRIFT</b>\n"
                f"Severity: {event['severity']}\n"
                f"Failures: {', '.join(failures[:4])}\n"
                f"Missing fills: {len(missing_in_sheets)} | "
                f"Inv match: {'yes' if inventory_match else 'no'} | "
                f"P&L mismatch days: {len(pnl_mismatch_days)}\n"
                f"Lookback: {args.lookback_min}m"
            )
            if args.enable_telegram_alerts and tg is not None:
                try:
                    tg.alert(msg)
                except Exception:
                    pass
            if args.log_alerts_to_sheets:
                try:
                    logger = sheets["logger"]
                    if logger is not None and logger.is_connected():
                        logger.log_alert("SYNC_AUDIT", msg.replace("<b>", "").replace("</b>", ""))
                except Exception:
                    pass

        if event["status"] == "PASS":
            return 0
        return 1
    except Exception as e:
        event["status"] = "ERROR"
        event["severity"] = "CRITICAL"
        event["error"] = str(e)
        event["latency_ms"] = round((time.monotonic() - t0) * 1000, 1)
        _append_jsonl(jsonl_path, event)
        consecutive_failures = int(state.get("consecutive_failures", 0)) + 1
        _write_json_file(
            state_path,
            {
                "consecutive_failures": consecutive_failures,
                "last_status": "ERROR",
                "last_severity": "CRITICAL",
                "last_ts": event["ts"],
                "last_error": str(e),
            },
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
