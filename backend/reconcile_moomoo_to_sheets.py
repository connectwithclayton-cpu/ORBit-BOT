"""
Reconcile PAPER account fills from Moomoo into canonical Sheets tabs:
- Broker Fills
- Reconciled Trades
- Open Inventory

Also keeps legacy Trades backfill in sync and regenerates dashboard from canonical
reconciled outputs.

Dry-run: prints intended actions only — does not append Trades, write backend/trade_data.json,
HTML, or replace canonical tabs. If broker open inventory disagrees with FIFO, exits before
dashboard save except when broker returns only zero-qty position rows (“ghost snapshot”):
then FIFO opens are used for the gate by default (see FABIO_STRICT_BROKER_POSITION_GATE).
"""

from __future__ import annotations

import datetime as dt
import os
import re
from collections import defaultdict, deque
from typing import Any, Dict, List, Tuple

from dotenv import load_dotenv

import moomoo as ft

from fabio_bot_paths import fabio_bot_root
from moomoo import OpenSecTradeContext, RET_OK, SecurityFirm, TrdEnv, TrdMarket

from dashboard_writer import (
    DashboardWriter,
    aggregate_closed_positions,
    normalize_and_validate_open_positions,
)
from exit_reasons import (
    REASON_SOURCE_RECONCILE,
    REASON_SOURCE_STRATEGY,
    canonical_exit_reason,
)
from manual_position_omissions import (
    is_omitted_reconcile_close_row,
    operator_omission_fifo_mismatch_messages,
)
from sheets_logger import (
    CREDS_PATH,
    HEADERS,
    SCOPES,
    SHEET_ID,
    TAB_BROKER_FILLS,
    TAB_OPEN_INVENTORY,
    TAB_RECON_TRADES,
    TAB_TRADES,
    GSPREAD_AVAILABLE,
    SheetsLogger,
)


def _safe_float(v, default=0.0) -> float:
    try:
        if v is None or v == "":
            return float(default)
        return float(v)
    except Exception:
        return float(default)


def _safe_int(v, default=0) -> int:
    try:
        if v is None or v == "":
            return int(default)
        return int(float(v))
    except Exception:
        return int(default)


def _hms(value: str) -> str:
    s = str(value or "").strip()
    if len(s) >= 19 and s[4] == "-" and s[7] == "-" and s[10] == " ":
        return s[11:19]
    return s[:8]


def _hms_to_seconds(hms: str) -> int | None:
    s = _hms(hms)
    if len(s) != 8 or s[2] != ":" or s[5] != ":":
        return None
    try:
        hh = int(s[0:2])
        mm = int(s[3:5])
        ss = int(s[6:8])
        return hh * 3600 + mm * 60 + ss
    except Exception:
        return None


def _parse_strategy_exit_rows_from_trades_sheet_rows(
    rows: List[List[str]],
    date: str | None = None,
) -> List[Dict]:
    """
    Extract strategy exit records from the Trades tab rows (excluding header).
    Expected (forward-only) schema includes:
      Exit Reason Code, Reason Source, Reason Detail as trailing columns.
    """
    out: List[Dict] = []
    for row in rows:
        r = list(row)
        row_date = str(r[0]).strip()
        if date and row_date != str(date):
            continue
        # Ensure at least 23 columns (post-schema add). Missing cols are treated as empty.
        if len(r) < 23:
            r = r + [""] * (23 - len(r))
        symbol = str(r[1]).strip().upper()
        direction = str(r[2]).strip().upper()
        entry_time = _hms(r[3])
        contracts = _safe_int(r[7], 0)
        exit_time = _hms(r[8])
        exit_reason_label = str(r[12]).strip()
        vix_value = _safe_float(r[13], 0.0)
        vix_regime = str(r[17]).strip()
        exit_reason_code = str(r[20]).strip().upper()
        reason_source = str(r[21]).strip().lower()
        reason_label_l = exit_reason_label.strip().lower()
        strategy_like = (
            reason_source == REASON_SOURCE_STRATEGY
            or (
                not reason_source
                and reason_label_l
                and reason_label_l not in {"reconciled fill close", "moomoo fill backfill", "open"}
                and vix_value > 0
            )
        )
        if not exit_time or exit_reason_label.upper() == "OPEN":
            continue
        if not strategy_like:
            continue
        if not symbol or not direction or contracts <= 0:
            continue
        out.append(
            {
                "symbol": symbol,
                "direction": direction,
                "contracts": contracts,
                "date": row_date,
                "entry_hms": entry_time,
                "exit_hms": exit_time,
                "exit_reason": exit_reason_label,
                "exit_reason_code": exit_reason_code,
                "reason_source": REASON_SOURCE_STRATEGY,
                "vix": vix_value,
                "vix_regime": vix_regime,
            }
        )
    return out


def _annotate_reconciled_dashboard_trades_with_strategy_exits(
    dashboard_trades: List[Dict],
    strategy_exits: List[Dict],
) -> int:
    """
    Overlay strategy exit reason onto reconciled CLOSE rows for analytics.
    Keeps fill provenance by setting fill_source='reconcile' on the row.
    Returns count of annotated rows.
    """
    if not dashboard_trades or not strategy_exits:
        return 0

    idx: Dict[tuple, List[Dict]] = defaultdict(list)
    idx_loose: Dict[tuple, List[Dict]] = defaultdict(list)
    for x in strategy_exits:
        date_key = str(x.get("date", "")).strip()
        sym_key = str(x.get("symbol", "")).upper()
        dir_key = str(x.get("direction", "")).upper()
        key = (
            date_key,
            sym_key,
            dir_key,
            _safe_int(x.get("contracts", 0), 0),
            _hms(str(x.get("entry_hms", ""))),
            _hms(str(x.get("exit_hms", ""))),
        )
        idx[key].append(x)
        idx_loose[(date_key, sym_key, dir_key)].append(x)

    # Date-level fallback context from strategy rows (for unmatched recon closes).
    day_vix_ctx: Dict[str, Dict[str, object]] = {}
    for x in strategy_exits:
        d = str(x.get("date", "")).strip()
        if not d:
            continue
        v = _safe_float(x.get("vix", 0.0), 0.0)
        vr = str(x.get("vix_regime", "")).strip()
        prev = day_vix_ctx.get(d, {})
        if v > 0 and not prev.get("vix"):
            prev["vix"] = v
        if vr and not prev.get("vix_regime"):
            prev["vix_regime"] = vr
        if prev:
            day_vix_ctx[d] = prev

    annotated = 0
    for t in dashboard_trades:
        if not isinstance(t, dict):
            continue
        if str(t.get("ledger_leg", "")).upper() != "CLOSE":
            continue
        key = (
            str(t.get("date", "")).strip(),
            str(t.get("symbol", "")).upper(),
            str(t.get("direction", "")).upper(),
            _safe_int(t.get("contracts", 0), 0),
            _hms(str(t.get("entry_time", ""))),
            _hms(str(t.get("exit_time", ""))),
        )
        cands = idx.get(key) or []
        # Fallback: if exact key misses (partial-fill qty drift, minor time mismatch),
        # use same-date/symbol/direction and pick closest by exit time.
        if not cands:
            cands = idx_loose.get(
                (
                    str(t.get("date", "")).strip(),
                    str(t.get("symbol", "")).upper(),
                    str(t.get("direction", "")).upper(),
                )
            ) or []
        if not cands:
            continue
        # If multiple matches, choose closest by exit time to be safe.
        tgt_sec = _hms_to_seconds(str(t.get("exit_time", "")))
        best = cands[0]
        if tgt_sec is not None and len(cands) > 1:
            best = min(
                cands,
                key=lambda r: abs((_hms_to_seconds(str(r.get("exit_hms", ""))) or tgt_sec) - tgt_sec),
            )

        er = canonical_exit_reason(
            str(best.get("exit_reason") or ""),
            source=REASON_SOURCE_STRATEGY,
            detail=f"annotated_from_sheets exit_reason_code={best.get('exit_reason_code','')}",
        )
        t["exit_reason"] = er.label
        t["exit_reason_code"] = str(best.get("exit_reason_code") or er.code).upper()
        t["reason_source"] = REASON_SOURCE_STRATEGY
        t["reason_detail"] = er.detail
        # Carry strategy context fields so dashboard analytics stay meaningful.
        t["vix"] = _safe_float(best.get("vix", t.get("vix", 0.0)), _safe_float(t.get("vix", 0.0)))
        if str(best.get("vix_regime", "")).strip():
            t["vix_regime"] = str(best.get("vix_regime", "")).strip()
        t["fill_source"] = REASON_SOURCE_RECONCILE
        annotated += 1

    # Fallback: preserve reconcile provenance, but backfill day VIX fields so table/chart
    # are not polluted by default 0.0/RECON when strategy snapshot exists for that date.
    for t in dashboard_trades:
        if not isinstance(t, dict):
            continue
        if str(t.get("ledger_leg", "")).upper() != "CLOSE":
            continue
        d = str(t.get("date", "")).strip()
        ctx = day_vix_ctx.get(d)
        if not ctx:
            continue
        cur_vix = _safe_float(t.get("vix", 0.0), 0.0)
        cur_reg = str(t.get("vix_regime", "")).strip()
        if cur_vix <= 0 and _safe_float(ctx.get("vix", 0.0), 0.0) > 0:
            t["vix"] = _safe_float(ctx.get("vix", 0.0), 0.0)
        if (not cur_reg or cur_reg.upper() == "RECON") and str(ctx.get("vix_regime", "")).strip():
            t["vix_regime"] = str(ctx.get("vix_regime", "")).strip()
    return annotated


def _apply_sheets_down_exit_reason_fallback(
    dashboard_trades: List[Dict],
    *,
    eod_start_hms: str = "15:40:00",
    eod_end_hms: str = "16:05:00",
) -> int:
    """
    If Sheets isn't reachable, label EOD-window reconciled closes as EOD close.
    Returns count of modified rows.
    """
    s0 = _hms_to_seconds(eod_start_hms) or 0
    s1 = _hms_to_seconds(eod_end_hms) or (24 * 3600 - 1)
    changed = 0
    for t in dashboard_trades or []:
        if not isinstance(t, dict):
            continue
        if str(t.get("ledger_leg", "")).upper() != "CLOSE":
            continue
        # Only apply to unreconciled/unknown logic rows.
        code = str(t.get("exit_reason_code", "")).strip().upper()
        if code and code != "RECONCILED_CLOSE":
            continue
        sec = _hms_to_seconds(str(t.get("exit_time", "")))
        if sec is None:
            continue
        if s0 <= sec <= s1:
            er = canonical_exit_reason("EOD close", source=REASON_SOURCE_STRATEGY, detail="fallback_sheets_down")
            t["exit_reason"] = er.label
            t["exit_reason_code"] = er.code
            t["reason_source"] = REASON_SOURCE_STRATEGY
            t["reason_detail"] = er.detail
            t["fill_source"] = REASON_SOURCE_RECONCILE
            changed += 1
    return changed

def _extract_symbol_and_direction(code: str, trd_side: str) -> Tuple[str, str]:
    code = str(code or "")
    underlying = code.split(".")[-1]
    m = re.match(r"([A-Z]+)\d{6}([CP])\d+", underlying)
    if m:
        symbol = m.group(1)
        direction = "CALL" if m.group(2) == "C" else "PUT"
        return symbol, direction

    # Fallback for non-option or unrecognized formats
    symbol = underlying[:8] if underlying else "UNKNOWN"
    if "SELL" in str(trd_side).upper():
        direction = "PUT"
    else:
        direction = "CALL"
    return symbol, direction


def _trade_row_key(row: List[str]) -> str:
    """
    Stable dedupe key focused on broker-originated identity.
    Prefer Notes fingerprint when present (source=moomoo_paper ...).
    """
    row = (row + [""] * 20)[:20]
    notes = str(row[19]).strip()
    date = str(row[0]).strip()
    contracts = str(_safe_int(row[7], 0))
    entry_px = f"{_safe_float(row[4], 0.0):.4f}"
    exit_px = f"{_safe_float(row[9], 0.0):.4f}"
    pnl = f"{_safe_float(row[10], 0.0):.2f}"
    side = "BUY" if str(row[3]).strip() else "SELL"
    if "source=moomoo_paper" in notes:
        # Includes broker code + side from source note.
        return f"{date}|{notes}|{contracts}|{entry_px}|{exit_px}|{pnl}"
    return f"{date}|{str(row[1]).strip()}|{str(row[2]).strip()}|{side}|{contracts}|{entry_px}|{exit_px}|{pnl}"


def _connect_sheet():
    if not GSPREAD_AVAILABLE:
        raise RuntimeError("gspread/google-auth not installed.")
    if not SHEET_ID or not CREDS_PATH:
        raise RuntimeError("GOOGLE_SHEET_ID or GOOGLE_CREDS_PATH not configured.")
    if not os.path.exists(CREDS_PATH):
        raise RuntimeError(f"Google creds file not found: {CREDS_PATH}")

    import gspread
    from google.oauth2.service_account import Credentials

    creds = Credentials.from_service_account_file(CREDS_PATH, scopes=SCOPES)
    gc = gspread.authorize(creds)
    sheet = gc.open_by_key(SHEET_ID)
    return sheet


def _fetch_all_paper_fills() -> List[Dict]:
    host = os.getenv("MOOMOO_HOST", "127.0.0.1")
    port = int(os.getenv("MOOMOO_PORT", "11111"))
    start_dt = "2020-01-01 00:00:00"
    end_dt = dt.datetime.now().strftime("%Y-%m-%d 23:59:59")

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

        records: List[Dict] = []
        for _, r in hist.iterrows():
            dealt_qty = _safe_int(r.get("dealt_qty", r.get("qty", 0)))
            if dealt_qty <= 0:
                continue
            ts = str(r.get("updated_time", r.get("create_time", "")))[:19]
            code = str(r.get("code", ""))
            trd_side = str(r.get("trd_side", ""))
            fill_id = f"{ts}|{code}|{trd_side}|{dealt_qty}|{_safe_float(r.get('dealt_avg_price', 0.0)):.4f}"
            symbol, direction = _extract_symbol_and_direction(code, trd_side)
            records.append(
                {
                    "fill_id": fill_id,
                    "code": code,
                    "symbol": symbol,
                    "direction": direction,
                    "trd_side": trd_side,
                    "qty": dealt_qty,
                    "avg_price": _safe_float(r.get("dealt_avg_price", 0.0)),
                    "time": ts,
                    "realized_pnl": _safe_float(r.get("realized_pl", r.get("realized_pnl", 0.0))),
                }
            )
        records.sort(key=lambda x: x["time"])
        return records
    finally:
        ctx.close()


def _env_explicit_simulate_acc_ids() -> List[int] | None:
    raw = (os.getenv("MOOMOO_SIMULATE_ACC_ID") or "").strip()
    if not raw:
        return None
    out: List[int] = []
    for part in raw.replace(",", " ").split():
        if part.isdigit():
            val = int(part)
            if val not in out:
                out.append(val)
    return out or None


def _discovered_simulate_acc_ids(ctx: OpenSecTradeContext) -> Tuple[List[int] | None, str]:
    """
    Prefer explicit paper acc ids via MOOMOO_SIMULATE_ACC_ID; else discover SIMULATE rows
    from get_acc_list. Returns (None, reason) when API says to use broker default routing.
    """
    forced = _env_explicit_simulate_acc_ids()
    if forced:
        return forced, "MOOMOO_SIMULATE_ACC_ID"
    ret_al, acc_df = ctx.get_acc_list()
    if ret_al != RET_OK:
        return None, f"get_acc_list_ret_{ret_al!r}"
    if acc_df is None or acc_df.empty:
        return None, "get_acc_list_empty_df"
    ids: List[int] = []
    for _, row in acc_df.iterrows():
        try:
            if row.get("trd_env") != TrdEnv.SIMULATE:
                continue
            aid = int(row.get("acc_id", 0))
        except (TypeError, ValueError):
            continue
        if aid > 0 and aid not in ids:
            ids.append(aid)
    if not ids:
        return None, "no_simulate_rows_in_acc_list"
    return ids, "discovered"


def _fetch_broker_open_inventory_with_meta() -> Tuple[Dict[str, int], Dict[str, Any]]:
    host = os.getenv("MOOMOO_HOST", "127.0.0.1")
    port = int(os.getenv("MOOMOO_PORT", "11111"))
    _refresh_raw = os.getenv("FABIO_POSITION_REFRESH_CACHE", "1").strip().lower()
    _refresh = _refresh_raw not in ("0", "false", "no", "")
    _supplement_raw = os.getenv("FABIO_SUPPLEMENT_POSITION_QUERY_ACC_ID_0", "1").strip().lower()
    _supplement_acc0 = _supplement_raw not in ("0", "false", "no", "")
    ctx = OpenSecTradeContext(
        filter_trdmarket=TrdMarket.US,
        host=host,
        port=port,
        security_firm=SecurityFirm.FUTUINC,
    )
    try:
        acc_ids_used, acc_source_tag = _discovered_simulate_acc_ids(ctx)

        queries: List[Tuple[Any, Any, Any]] = []
        if acc_ids_used is not None:
            for aid in acc_ids_used:
                ret_i, df_i = ctx.position_list_query(
                    trd_env=TrdEnv.SIMULATE,
                    acc_id=int(aid),
                    acc_index=0,
                    position_market=TrdMarket.NONE,
                    refresh_cache=_refresh,
                )
                queries.append((aid, ret_i, df_i))
            if _supplement_acc0:
                ret_s, df_s = ctx.position_list_query(
                    trd_env=TrdEnv.SIMULATE,
                    acc_id=0,
                    acc_index=0,
                    position_market=TrdMarket.NONE,
                    refresh_cache=_refresh,
                )
                queries.append(("supplement_acc_id_0_idx_0", ret_s, df_s))
        else:
            ret_0, pos_0 = ctx.position_list_query(
                trd_env=TrdEnv.SIMULATE,
                position_market=TrdMarket.NONE,
                refresh_cache=_refresh,
            )
            queries.append(("default", ret_0, pos_0))

        per_q: List[dict[str, object]] = []
        for label, rq, dq in queries:
            n = None
            if dq is not None and hasattr(dq, "shape"):
                try:
                    n = int(dq.shape[0])
                except Exception:
                    n = None
            per_q.append({"label": str(label), "ret": str(rq), "ret_ok": rq == RET_OK, "nrow": n})

        nrow_total = sum(
            int(p["nrow"] or 0)
            for p in per_q
            if isinstance(p.get("nrow"), int)
        )

        ok_frames = [(lab, dq) for lab, rq, dq in queries if rq == RET_OK and dq is not None]
        if not ok_frames or all(getattr(df, "empty", True) for _, df in ok_frames):
            any_bad = [(lab, rq) for lab, rq, dq in queries if rq != RET_OK]
            if any_bad:
                print(
                    f"[reconcile] position_list_query failed for {len(any_bad)} account query(ies): "
                    f"{any_bad[0][1]!r}. "
                    "Open positions will not match FIFO until this succeeds."
                )
            else:
                print(
                    "[reconcile] position_list_query returned no rows for SIMULATE. "
                    "If you hold paper positions, confirm Moomoo OpenD is running and logged in."
                )
            empty_meta = {
                "ghost_only_snapshot": False,
                "nrow_total": nrow_total,
                "per_query": per_q,
                "acc_source": acc_source_tag,
                "simulate_acc_ids": acc_ids_used,
            }
            return {}, empty_meta

        out: Dict[str, int] = defaultdict(int)
        dropped_zero_qty = 0
        used_can_sell_fallback = 0
        normalized_negative_qty = 0

        for _, df in ok_frames:
            if getattr(df, "empty", True):
                continue
            for _, r in df.iterrows():
                code = str(r.get("code", "")).strip() if hasattr(r, "get") else ""
                qty = _safe_int(r.get("qty", 0) if hasattr(r, "get") else 0, 0)
                if qty < 0:
                    qty = abs(qty)
                    normalized_negative_qty += 1
                if qty <= 0:
                    csq = _safe_int(
                        r.get("can_sell_qty", 0) if hasattr(r, "get") else 0,
                        0,
                    )
                    if csq > 0:
                        qty = csq
                        used_can_sell_fallback += 1
                if code and qty > 0:
                    out[code] = max(out[code], qty)
                elif code:
                    dropped_zero_qty += 1

        out_plain = dict(out)
        snap_meta: Dict[str, Any] = {
            "ghost_only_snapshot": bool(nrow_total > 0 and len(out_plain) == 0),
            "nrow_total": nrow_total,
            "per_query": per_q,
            "supplement_acc_id_0_done": bool(acc_ids_used is not None and _supplement_acc0),
            "acc_source": acc_source_tag,
            "simulate_acc_ids": acc_ids_used,
            "dropped_zero_qty_lines": dropped_zero_qty,
            "used_can_sell_fallback": used_can_sell_fallback,
            "normalized_negative_qty": normalized_negative_qty,
        }
        return out_plain, snap_meta
    finally:
        ctx.close()


def _fetch_broker_open_inventory() -> Dict[str, int]:
    inv, _meta = _fetch_broker_open_inventory_with_meta()
    return inv


def _broker_open_dict_to_dashboard_opens(broker_open: Dict[str, int]) -> List[Dict]:
    """
    Convert broker code->qty snapshot into dashboard open_positions shape.
    Uses broker code→qty snapshot (or FIFO fallback when reconcile enables gate trust).
    """
    today = dt.date.today().isoformat()
    out: List[Dict] = []
    for code, qty in sorted((broker_open or {}).items()):
        q = _safe_int(qty, 0)
        if q <= 0:
            continue
        symbol, direction = _extract_symbol_and_direction(str(code), "BUY")
        out.append(
            {
                "date": today,
                "symbol": symbol,
                "direction": direction,
                "entry_time": "—",
                "entry_price": 0.0,
                "contracts": q,
                "vix": 0.0,
                "or_atr_pct": 0.0,
                "notes": f"broker code={code}",
            }
        )
    return out


def _to_broker_fill_rows(records: List[Dict]) -> List[List]:
    rows = []
    for rec in records:
        qty = _safe_int(rec["qty"])
        price = _safe_float(rec["avg_price"])
        rows.append(
            [
                rec["fill_id"],
                rec["time"],
                rec["time"][:10],
                rec["code"],
                rec["symbol"],
                rec["direction"],
                rec["trd_side"],
                qty,
                round(price, 4),
                round(qty * price * 100, 2),
                round(_safe_float(rec["realized_pnl"]), 2),
                "moomoo_paper",
            ]
        )
    return rows


def _reconcile_fifo(records: List[Dict]) -> Tuple[List[List], List[List]]:
    lots: Dict[str, deque] = defaultdict(deque)
    closed_rows: List[List] = []
    for rec in records:
        code = rec["code"]
        qty = _safe_int(rec["qty"])
        price = _safe_float(rec["avg_price"])
        side = rec["trd_side"].upper()
        if qty <= 0:
            continue
        if "BUY" in side:
            lots[code].append(
                {
                    "remaining_qty": qty,
                    "entry_price": price,
                    "entry_time": rec["time"],
                    "symbol": rec["symbol"],
                    "direction": rec["direction"],
                }
            )
            continue
        # SELL: pair against oldest lots for this contract code
        remaining = qty
        while remaining > 0 and lots[code]:
            lot = lots[code][0]
            matched = min(remaining, int(lot["remaining_qty"]))
            entry_price = _safe_float(lot["entry_price"])
            pnl = (price - entry_price) * matched * 100
            ret_pct = ((price - entry_price) / entry_price * 100) if entry_price > 0 else 0.0
            closed_rows.append(
                [
                    rec["time"],
                    rec["time"][:10],
                    code,
                    lot["symbol"],
                    lot["direction"],
                    matched,
                    lot["entry_time"],
                    round(entry_price, 4),
                    rec["time"],
                    round(price, 4),
                    round(pnl, 2),
                    round(ret_pct, 2),
                    "moomoo_paper_fifo",
                ]
            )
            lot["remaining_qty"] = int(lot["remaining_qty"]) - matched
            remaining -= matched
            if lot["remaining_qty"] <= 0:
                lots[code].popleft()
        # Ignore oversell remainder (data anomalies), invariants will catch mismatch.

    open_rows: List[List] = []
    now_ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for code, q in lots.items():
        for lot in q:
            rq = int(lot["remaining_qty"])
            if rq <= 0:
                continue
            ep = _safe_float(lot["entry_price"])
            open_rows.append(
                [
                    now_ts,
                    lot["entry_time"][:10],
                    code,
                    lot["symbol"],
                    lot["direction"],
                    rq,
                    lot["entry_time"],
                    round(ep, 4),
                    round(rq * ep * 100, 2),
                    "moomoo_paper_fifo",
                ]
            )
    return closed_rows, open_rows


def _is_manually_omitted_recon_row(row: List) -> bool:
    """
    Match reconciled close rows against an explicit manual omission list.
    Shape for `row`:
    [time, date, code, symbol, direction, qty, entry_time, entry_px, exit_time, exit_px, pnl, ret, note]
    """
    return is_omitted_reconcile_close_row(row)


def _omitted_position_refs_from_recon_rows(recon_rows: List[List]) -> List[Dict]:
    """
    Build concrete omission refs from already-matched recon rows so we can also
    suppress legacy Trades backfill and Broker Fills interpretations for the same
    position lifecycle.
    """
    refs: List[Dict] = []
    for r in recon_rows:
        if not _is_manually_omitted_recon_row(r):
            continue
        v = (list(r) + [""] * 13)[:13]
        refs.append(
            {
                "code": str(v[2]).strip(),
                "entry_ts": str(v[6]).strip(),
                "exit_ts": str(v[8]).strip(),
                "qty": _safe_int(v[5], 0),
            }
        )
    return refs


def _is_moomoo_record_manually_omitted(rec: Dict, refs: List[Dict]) -> bool:
    """
    Suppress raw Moomoo fills linked to omitted reconciled positions.
    Uses concrete code+timestamp refs extracted from FIFO-matched rows.
    """
    code = str(rec.get("code", "")).strip()
    ts = str(rec.get("time", "")).strip()
    qty = _safe_int(rec.get("qty", 0), 0)
    if not code or not ts:
        return False
    for ref in refs:
        if code != str(ref.get("code", "")).strip():
            continue
        if ts not in {str(ref.get("entry_ts", "")).strip(), str(ref.get("exit_ts", "")).strip()}:
            continue
        rq = _safe_int(ref.get("qty", 0), 0)
        if rq > 0 and qty > rq:
            continue
        return True
    return False


def _moomoo_records_to_sheet_rows(records: List[Dict]) -> List[List]:
    rows = []
    for rec in records:
        ts = rec["time"] or ""
        date = ts[:10] if len(ts) >= 10 else ""
        hhmmss = ts[11:19] if len(ts) >= 19 else ""
        symbol, direction = _extract_symbol_and_direction(rec["code"], rec["trd_side"])
        is_buy = "BUY" in str(rec["trd_side"]).upper()
        price = round(_safe_float(rec["avg_price"]), 4)

        er = canonical_exit_reason("Reconciled fill close", source=REASON_SOURCE_RECONCILE)
        # Map broker fill into existing Trades schema.
        # Unknown strategy fields are left blank and tagged in Notes.
        row = [
            date,                       # Date
            symbol,                     # Symbol
            direction,                  # Direction (parsed from option code if possible)
            hhmmss if is_buy else "",   # Entry Time
            price if is_buy else "",    # Entry Price ($)
            "",                         # Strike
            "",                         # Expiry
            _safe_int(rec["qty"]),      # Contracts
            "" if is_buy else hhmmss,   # Exit Time
            "" if is_buy else price,    # Exit Price ($)
            round(_safe_float(rec["realized_pnl"]), 2) if not is_buy else "",  # P&L ($)
            "",                         # Return (%)
            "Moomoo fill backfill",     # Exit Reason
            "",                         # VIX
            "",                         # OR/ATR (%)
            "",                         # Capital After ($)
            "",                         # Trend
            "",                         # VIX Regime
            "",                         # Day Color
            f"source=moomoo_paper code={rec['code']} side={rec['trd_side']}",
            er.code,                    # Exit Reason Code
            er.source,                  # Reason Source
            er.detail,                  # Reason Detail
        ]
        rows.append(row)
    return rows


def _canonical_to_dashboard_trades(recon_rows: List[List], open_rows: List[List]) -> Tuple[List[Dict], List[Dict]]:
    filled = []
    for r in recon_rows:
        v = (list(r) + [""] * 13)[:13]
        er = canonical_exit_reason("Reconciled fill close", source=REASON_SOURCE_RECONCILE)
        filled.append(
            {
                "date": v[1],
                "symbol": v[3],
                "direction": v[4],
                "entry_time": str(v[6])[11:19] if len(str(v[6])) >= 19 else str(v[6]),
                "entry_price": _safe_float(v[7]),
                "exit_time": str(v[8])[11:19] if len(str(v[8])) >= 19 else str(v[8]),
                "exit_price": _safe_float(v[9]),
                "pnl": _safe_float(v[10]),
                "pnl_position_total": _safe_float(v[10]),
                "pnl_leg": _safe_float(v[10]),
                "return_pct": _safe_float(v[11]),
                "exit_reason": er.label,
                "exit_reason_code": er.code,
                "reason_source": er.source,
                "reason_detail": er.detail,
                "contracts": _safe_int(v[5]),
                "ledger_leg": "CLOSE",
                "ledger_side": "SELL",
                "qty_leg": _safe_int(v[5]),
                "qty_after": 0,
                "include_in_session_pnl": True,
                "vix": 0.0,
                "or_atr_pct": 0.0,
                "trend": "RECON",
                "vix_regime": "RECON",
                "day_color": "RECON",
                "notes": v[12],
            }
        )
    open_positions = []
    for r in open_rows:
        v = (list(r) + [""] * 10)[:10]
        open_positions.append(
            {
                "date": v[1],
                "symbol": v[3],
                "direction": v[4],
                "entry_time": str(v[6])[11:19] if len(str(v[6])) >= 19 else str(v[6]),
                "entry_price": _safe_float(v[7]),
                "contracts": _safe_int(v[5]),
                "vix": 0.0,
                "or_atr_pct": 0.0,
                "notes": v[9],
            }
        )
    return filled, open_positions


def _build_daily(trades: List[Dict]) -> List[Dict]:
    grouped: Dict[str, List[Dict]] = defaultdict(list)
    for p in aggregate_closed_positions(trades):
        d = p.get("date") or ""
        if not d:
            continue
        grouped[d].append(p)

    daily = []
    for d in sorted(grouped.keys()):
        plist = grouped[d]
        pnls = [_safe_float(p.get("pnl"), 0.0) for p in plist]
        winners = [x for x in pnls if x > 0]
        losers = [x for x in pnls if x < 0]
        total = len(plist)
        net = round(sum(pnls), 2)
        wr = round((len(winners) / total) * 100, 1) if total else 0.0
        daily.append(
            {
                "date": d,
                "total_trades": total,
                "winners": len(winners),
                "losers": len(losers),
                "win_rate": wr,
                "net_pnl": net,
                "gross_win": round(sum(winners), 2),
                "gross_loss": round(sum(losers), 2),
                "capital": 0.0,
                "daily_return": 0.0,
                "proven_edge": round(net / total, 2) if total else 0.0,
            }
        )
    return daily


def main():
    load_dotenv(fabio_bot_root() / ".env")
    dry_run = "--dry-run" in os.sys.argv

    print("Fetching PAPER fills from Moomoo...")
    moomoo_records = _fetch_all_paper_fills()
    print(f"Fetched {len(moomoo_records)} filled order records.")

    print("Connecting to Google Sheet...")
    sheet = _connect_sheet()
    logger = SheetsLogger()
    if not logger.is_connected():
        raise RuntimeError("SheetsLogger is not connected; cannot publish canonical tabs.")

    recon_rows_all, open_inventory_rows = _reconcile_fifo(moomoo_records)
    for _om_msg in operator_omission_fifo_mismatch_messages(recon_rows_all):
        print(f"⚠ [reconcile] {_om_msg}")
        if logger.is_connected():
            logger.log_alert("OMISSION_SPEC", _om_msg, "")
    omitted_refs = _omitted_position_refs_from_recon_rows(recon_rows_all)
    moomoo_records_effective = [
        rec for rec in moomoo_records if not _is_moomoo_record_manually_omitted(rec, omitted_refs)
    ]

    # Legacy backfill to Trades (kept for compatibility/audit)
    ws = sheet.worksheet(TAB_TRADES)
    existing = ws.get_all_values()
    existing_rows = existing[1:] if len(existing) > 1 else []
    existing_keys = {_trade_row_key((r + [""] * 20)[:20]) for r in existing_rows}
    candidate_rows = _moomoo_records_to_sheet_rows(moomoo_records_effective)
    missing_rows = [r for r in candidate_rows if _trade_row_key(r) not in existing_keys]

    print(f"Current Trades rows in sheet: {len(existing_rows)}")
    print(f"Candidate rows from Moomoo:   {len(candidate_rows)}")
    print(f"Missing rows to append:       {len(missing_rows)}")

    if missing_rows and not dry_run:
        ws.append_rows(missing_rows, value_input_option="USER_ENTERED")
        print(f"Appended {len(missing_rows)} missing rows to Trades.")
    elif dry_run:
        print("Dry-run mode: no sheet writes performed.")

    broker_fill_rows = _to_broker_fill_rows(moomoo_records_effective)
    recon_rows = [r for r in recon_rows_all if not _is_manually_omitted_recon_row(r)]
    omitted_count = len(recon_rows_all) - len(recon_rows)
    if omitted_count:
        print(
            f"[reconcile] Manually omitted {omitted_count} reconciled position(s) "
            "from canonical outputs."
        )

    # Invariant: computed open inventory must match broker open positions by code.
    broker_open, broker_snap_meta = _fetch_broker_open_inventory_with_meta()
    # Dashboard JSON/HTML: only rows the broker reports with positive effective qty.
    # When ghost_only_snapshot triggers FIFO trust below, broker_open may be replaced
    # for the gate — we still persist this snapshot for trade_data open_positions.
    dashboard_opens_from_broker = dict(broker_open)

    computed_open: Dict[str, int] = defaultdict(int)
    for r in open_inventory_rows:
        computed_open[str(r[2])] += _safe_int(r[5])

    strict_broker_gate = (
        os.getenv("FABIO_STRICT_BROKER_POSITION_GATE", "").strip().lower()
        in ("1", "true", "yes")
    )
    env_trust_fifo_on_ghost_snap = (
        os.getenv(
            "FABIO_RECONCILE_TRUST_FIFO_IF_BROKER_ROWS_ALL_ZERO_QTY", ""
        ).strip().lower()
        in ("1", "true", "yes")
    )
    if broker_snap_meta.get("ghost_only_snapshot"):
        print(
            "[reconcile] Broker position_list_query returned rows, but each line had qty 0 "
            "and can_sell_qty 0 (OpenD paper snapshot inconsistent with fills / UI)."
        )
        if strict_broker_gate:
            print(
                "[reconcile] FABIO_STRICT_BROKER_POSITION_GATE is on — reconcile will refuse "
                "unless you set FABIO_RECONCILE_TRUST_FIFO_IF_BROKER_ROWS_ALL_ZERO_QTY=1 "
                "(or unset strict and rely on default FIFO fallback for ghost-only snapshots)."
            )
        else:
            print(
                "[reconcile] Default: reconcile gate will align to FIFO-derived opens when "
                "they disagree; set FABIO_STRICT_BROKER_POSITION_GATE=1 to forbid that."
            )

    broker_keys = set(broker_open.keys())
    comp_keys = set(computed_open.keys())
    mismatch = broker_keys != comp_keys or any(
        _safe_int(broker_open.get(k, 0)) != _safe_int(computed_open.get(k, 0))
        for k in broker_keys.union(comp_keys)
    )

    allow_fifo_trust_on_ghost = (
        bool(computed_open)
        and broker_snap_meta.get("ghost_only_snapshot")
        and ((not strict_broker_gate) or env_trust_fifo_on_ghost_snap)
    )
    if mismatch and allow_fifo_trust_on_ghost:
        mode = (
            "explicit env FABIO_RECONCILE_TRUST_FIFO_IF_BROKER_ROWS_ALL_ZERO_QTY "
            "(strict broker gate)"
            if strict_broker_gate
            else "default FIFO fallback (non-strict gate)"
        )
        trust_msg = (
            f"RECONCILE gate: using FIFO-derived opens — broker snapshot rows had zero effective "
            f"qty (position_list_query nrow={broker_snap_meta.get('nrow_total')}). Mode: {mode}."
        )
        print(f"[reconcile] {trust_msg}")
        print(
            "[reconcile] backend/trade_data.json/HTML open_positions will remain broker-only (empty if "
            "no positive qty); Open Inventory sheet tab still reflects FIFO-derived lots."
        )
        if logger.is_connected():
            logger.log_alert("RECONCILE_GATE_FIFO_TRUST", trust_msg, "")
        broker_open = dict(computed_open)
        broker_keys = set(broker_open.keys())
        mismatch = broker_keys != comp_keys or any(
            _safe_int(broker_open.get(k, 0)) != _safe_int(computed_open.get(k, 0))
            for k in broker_keys.union(comp_keys)
        )

    if mismatch:
        detail = (
            "reconcile mismatch: broker_open="
            f"{dict(broker_open)} computed_open={dict(computed_open)}"
        )
        print(f"✗ {detail}")
        print(
            "⚠ Broker vs FIFO opens disagree — backend/trade_data.json (dashboard) and canonical Sheets "
            "tabs were NOT updated. Fix OpenD/paper position visibility or investigate inventory; "
            "rerun reconcile."
        )
        if logger.is_connected():
            logger.log_alert("RECONCILE_MISMATCH", detail, "")
        return 1

    dashboard_trades, _dashboard_open_positions_fifo = _canonical_to_dashboard_trades(
        recon_rows, open_inventory_rows
    )
    dashboard_open_positions, _ = normalize_and_validate_open_positions(
        _broker_open_dict_to_dashboard_opens(dashboard_opens_from_broker)
    )

    # Annotate reconciled closes with strategy exit reasons from same-day Sheets Trades logs.
    try:
        strategy_exits = _parse_strategy_exit_rows_from_trades_sheet_rows(
            existing_rows
        )
        n_ann = _annotate_reconciled_dashboard_trades_with_strategy_exits(
            dashboard_trades, strategy_exits
        )
        if n_ann:
            print(
                f"[reconcile] Annotated {n_ann} reconciled close(s) with strategy exit reasons."
            )
    except Exception as e:
        n_fb = _apply_sheets_down_exit_reason_fallback(dashboard_trades)
        print(f"[reconcile] Strategy-exit annotation skipped ({e}); fallback_eod_labeled={n_fb}.")
        if logger.is_connected():
            logger.log_alert("RECONCILE", f"Strategy-exit annotation skipped: {e}", "")

    dashboard_daily = _build_daily(dashboard_trades)

    base_msg = (
        "Dashboard regenerated from FIFO-reconciled Moomoo fills "
        f"({len(dashboard_trades)} closed-row(s) in dashboard store)."
    )

    if dry_run:
        print(base_msg.replace("regenerated", "would regenerate (dry-run)"))
        print(
            f"[dry-run] Would write {TAB_BROKER_FILLS}/{TAB_RECON_TRADES}/{TAB_OPEN_INVENTORY} "
            f"({len(broker_fill_rows)} broker rows, {len(recon_rows)} recon closes)."
        )
        print("Dry-run: no changes to backend/trade_data.json, HTML, or Sheets.")
        return 0

    writer = DashboardWriter()
    writer._data = {
        "trades": dashboard_trades,
        "daily": dashboard_daily,
        "open_positions": dashboard_open_positions,
    }
    writer._save()
    writer._write_html()
    print(base_msg)

    ok_bf = logger.replace_tab_rows(TAB_BROKER_FILLS, HEADERS[TAB_BROKER_FILLS], broker_fill_rows)
    ok_rt = logger.replace_tab_rows(TAB_RECON_TRADES, HEADERS[TAB_RECON_TRADES], recon_rows)
    ok_oi = logger.replace_tab_rows(TAB_OPEN_INVENTORY, HEADERS[TAB_OPEN_INVENTORY], open_inventory_rows)
    if ok_bf and ok_rt and ok_oi:
        print("Sheets canonical tabs updated.")
        return 0

    msg = (
        f"canonical tab write incomplete (broker_fills={ok_bf}, "
        f"recon_trades={ok_rt}, open_inventory={ok_oi})"
    )
    print(f"✗ {msg}")
    if logger.is_connected():
        logger.log_alert("CANONICAL_PUBLISH", msg, "")
    return 1


if __name__ == "__main__":
    try:
        _rc = main()
    except RuntimeError as e:
        print(f"ERROR: {e}")
        _rc = 2
    except Exception:
        import traceback

        traceback.print_exc()
        _rc = 2
    else:
        if _rc is None:
            _rc = 0
    raise SystemExit(_rc)
