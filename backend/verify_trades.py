"""
verify_trades.py — Pull today's actual fills from Moomoo OpenD
and compare against what's recorded in trade_data.json.

Usage:
    python3 verify_trades.py
    python3 verify_trades.py --live      # force live mode
    python3 verify_trades.py --paper     # force paper mode
    python3 verify_trades.py --date 2026-05-06   # specific date
"""

import os
import sys
import json
import pathlib
import datetime

_FABIO_ROOT = pathlib.Path(__file__).resolve().parent.parent

# ── Load .env ─────────────────────────────────────────────────────────────────
def _load_env():
    for p in [
        _FABIO_ROOT / ".env",
        pathlib.Path.home() / "Documents" / "TRADING" / "Fabio_bot" / ".env",
    ]:
        if p.exists():
            for line in p.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
            break

_load_env()

import moomoo as ft
from moomoo import OpenSecTradeContext, TrdMarket, TrdEnv, SecurityFirm, RET_OK

# ── Config ────────────────────────────────────────────────────────────────────
MOOMOO_HOST = os.getenv("MOOMOO_HOST", "127.0.0.1")
MOOMOO_PORT = int(os.getenv("MOOMOO_PORT", "11111"))
DATA_FILE   = _FABIO_ROOT / "trade_data.json"

_env_flag = os.getenv("MOOMOO_TRADE_ENV", "SIMULATE").upper()
if "--live" in sys.argv:
    TRADE_ENV = TrdEnv.REAL
    print("⚠️  LIVE mode")
elif "--paper" in sys.argv:
    TRADE_ENV = TrdEnv.SIMULATE
    print("📄 PAPER mode")
else:
    TRADE_ENV = TrdEnv.REAL if _env_flag == "REAL" else TrdEnv.SIMULATE
    mode = "LIVE" if TRADE_ENV == TrdEnv.REAL else "PAPER"
    print(f"📄 Mode from .env: {mode}")

# Date to check
target_date = datetime.date.today().isoformat()
for arg in sys.argv[1:]:
    if arg.startswith("--date"):
        # --date 2026-05-06 or --date=2026-05-06
        parts = arg.split("=") if "=" in arg else [arg, sys.argv[sys.argv.index(arg) + 1]]
        target_date = parts[1].strip()
        break

print(f"📅 Checking date: {target_date}\n")

# ── Connect ───────────────────────────────────────────────────────────────────
try:
    ctx = OpenSecTradeContext(
        filter_trdmarket=TrdMarket.US,
        host=MOOMOO_HOST,
        port=MOOMOO_PORT,
        security_firm=SecurityFirm.FUTUINC
    )
except Exception as e:
    print(f"❌ Could not connect to OpenD: {e}")
    print("   Make sure Moomoo OpenD is running.")
    sys.exit(1)

try:
    # ── 1. Today's filled orders ──────────────────────────────────────────────
    print("═" * 60)
    print("  MOOMOO: TODAY'S FILLED ORDERS")
    print("═" * 60)

    ret, orders = ctx.order_list_query(trd_env=TRADE_ENV)
    if ret != RET_OK:
        print(f"❌ order_list_query failed: {orders}")
    else:
        if orders.empty:
            print("  No orders found.")
        else:
            # Filter for today and filled status
            filled = orders[
                orders.get("dealt_qty", orders.get("qty", 0)) > 0
            ] if not orders.empty else orders

            cols_want = ["code", "trd_side", "order_type", "order_status",
                         "qty", "dealt_qty", "dealt_avg_price",
                         "create_time", "updated_time"]
            cols_show = [c for c in cols_want if c in orders.columns]

            if filled.empty:
                print("  No filled orders found for today.")
            else:
                print(f"  {len(filled)} order(s) found:\n")
                for _, row in filled.iterrows():
                    side  = row.get("trd_side", "?")
                    code  = row.get("code", "?")
                    qty   = row.get("qty", 0)
                    dealt = row.get("dealt_qty", 0)
                    price = row.get("dealt_avg_price", 0)
                    ctime = str(row.get("create_time", ""))[:19]
                    utime = str(row.get("updated_time", ""))[:19]
                    status = row.get("order_status", "?")
                    print(f"  {side:5s} {code:20s} qty={qty} dealt={dealt} "
                          f"avg_px={price:.3f}  created={ctime}  updated={utime}  [{status}]")

    # ── 2. Deal list (individual fills) ──────────────────────────────────────
    print()
    print("═" * 60)
    print("  MOOMOO: INDIVIDUAL FILLS (deal_list_query)")
    print("═" * 60)

    ret2, deals = ctx.deal_list_query(trd_env=TRADE_ENV)
    if ret2 != RET_OK:
        print(f"❌ deal_list_query failed: {deals}")
    else:
        if deals.empty:
            print("  No deals found.")
        else:
            print(f"  {len(deals)} fill(s) returned:\n")
            for _, row in deals.iterrows():
                side  = row.get("trd_side", "?")
                code  = row.get("code", "?")
                qty   = row.get("qty", 0)
                price = row.get("price", 0)
                dtime = str(row.get("create_time", ""))[:19]
                print(f"  {side:5s} {code:20s} qty={qty} price={price:.3f}  time={dtime}")

    # ── 3. History orders (catches yesterday's carryovers) ────────────────────
    print()
    print("═" * 60)
    print("  MOOMOO: HISTORY ORDERS (past 7 days)")
    print("═" * 60)

    start_dt = (datetime.date.today() - datetime.timedelta(days=7)).strftime("%Y-%m-%d 00:00:00")
    end_dt   = datetime.date.today().strftime("%Y-%m-%d 23:59:59")

    ret3, hist = ctx.history_order_list_query(
        status_filter_list=[ft.OrderStatus.FILLED_ALL, ft.OrderStatus.FILLED_PART],
        start=start_dt,
        end=end_dt,
        trd_env=TRADE_ENV
    )
    if ret3 != RET_OK:
        print(f"❌ history_order_list_query failed: {hist}")
    else:
        if hist.empty:
            print("  No historical filled orders.")
        else:
            # Filter for today
            today_hist = hist[hist.get("create_time", "").astype(str).str.startswith(target_date)] \
                if "create_time" in hist.columns else hist
            print(f"  {len(today_hist)} filled order(s) for {target_date}:\n")
            for _, row in today_hist.iterrows():
                side  = row.get("trd_side", "?")
                code  = row.get("code", "?")
                qty   = row.get("qty", 0)
                dealt = row.get("dealt_qty", 0)
                price = row.get("dealt_avg_price", 0)
                ctime = str(row.get("create_time", ""))[:19]
                status = row.get("order_status", "?")
                print(f"  {side:5s} {code:20s} qty={qty} dealt={dealt} "
                      f"avg_px={price:.3f}  created={ctime}  [{status}]")

    # ── 4. Compare to trade_data.json ─────────────────────────────────────────
    print()
    print("═" * 60)
    print(f"  RECORDED IN trade_data.json for {target_date}")
    print("═" * 60)

    if DATA_FILE.exists():
        data = json.loads(DATA_FILE.read_text())
        recorded = [t for t in data.get("trades", []) if t.get("date", "").startswith(target_date)]
        if recorded:
            for t in recorded:
                print(f"  {t['direction']:5s} {t['symbol']:6s} "
                      f"entry={t['entry_time']} exit={t['exit_time']} "
                      f"qty={t['contracts']} pnl=${t['pnl']:+,.0f}  reason={t['exit_reason']}")
        else:
            print(f"  No trades recorded for {target_date}")
    else:
        print("  trade_data.json not found.")

    print()
    print("✅ Verification complete.")

finally:
    ctx.close()
