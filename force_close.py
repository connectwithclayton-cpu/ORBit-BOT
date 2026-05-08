"""
force_close.py — Standalone emergency position closer for Fabio ORB bot.
Connects to Moomoo OpenD, fetches all open US option positions, and
places market sell orders for every one.

Usage:
    python3 force_close.py
    python3 force_close.py --paper     # force paper-trading mode
    python3 force_close.py --live      # force live-trading mode
"""

import os
import sys
import pathlib
import time

# ── Load .env ────────────────────────────────────────────────────────────────
def _load_env():
    for p in [
        pathlib.Path(__file__).parent / ".env",
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
from moomoo import (
    OpenSecTradeContext, TrdMarket, TrdEnv, TrdSide,
    OrderType, SecurityFirm, RET_OK
)

# ── Config (mirrors orb_bot_fabio.py) ────────────────────────────────────────
MOOMOO_HOST  = os.getenv("MOOMOO_HOST", "127.0.0.1")
MOOMOO_PORT  = int(os.getenv("MOOMOO_PORT", "11111"))

_env_flag = os.getenv("MOOMOO_TRADE_ENV", "SIMULATE").upper()
if "--live" in sys.argv:
    TRADE_ENV = TrdEnv.REAL
    print("⚠️  LIVE mode — real money")
elif "--paper" in sys.argv:
    TRADE_ENV = TrdEnv.SIMULATE
    print("📄 PAPER mode")
else:
    TRADE_ENV = TrdEnv.REAL if _env_flag == "REAL" else TrdEnv.SIMULATE
    mode = "LIVE" if TRADE_ENV == TrdEnv.REAL else "PAPER"
    print(f"📄 Mode from .env: {mode}")

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("\n🔴 FORCE CLOSE — connecting to Moomoo OpenD...")
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
        # ── Fetch open positions ───────────────────────────────────────────
        ret, data = ctx.position_list_query(trd_env=TRADE_ENV)
        if ret != RET_OK:
            print(f"❌ Could not fetch positions: {data}")
            sys.exit(1)

        if data.empty:
            print("✅ No open positions found — nothing to close.")
            return

        def _f(val, default=0.0):
            try:
                return float(val)
            except (TypeError, ValueError):
                return default

        print(f"\n  Found {len(data)} open position(s):\n")
        for _, row in data.iterrows():
            code = row.get("code", "")
            qty  = int(_f(row.get("qty", 0)))
            cost = _f(row.get("cost_price", 0))
            cur  = _f(row.get("last_price", 0))
            pnl  = _f(row.get("unrealized_pl", 0))
            pnl_str = f"${pnl:+.2f}" if pnl != 0.0 else "N/A"
            print(f"  {code} | qty={qty} | cost={cost:.2f} | last={cur:.2f} | unreal P&L={pnl_str}")

        print()
        if "--force" in sys.argv:
            print("  --force flag set — skipping confirmation.")
        else:
            confirm = input("  Sell ALL positions above? (yes/no): ").strip().lower()
            if confirm not in ("yes", "y"):
                print("  Aborted — no orders placed.")
                return

        print()
        closed = 0
        failed = 0

        for _, row in data.iterrows():
            code = row.get("code", "")
            qty  = int(float(row.get("qty", 0) or 0))
            if qty <= 0:
                continue

            print(f"  → Selling {qty}x {code} at market...")
            ret, order = ctx.place_order(
                price        = 0,
                qty          = qty,
                code         = code,
                trd_side     = TrdSide.SELL,
                order_type   = OrderType.MARKET,
                trd_env      = TRADE_ENV,
                acc_id       = 0,
                adjust_limit = 0,
            )
            if ret == RET_OK:
                print(f"    ✓ Sell order placed")
                closed += 1
            else:
                print(f"    ❌ Order failed: {order}")
                failed += 1

            time.sleep(0.5)   # brief pause between orders

        print(f"\n  Done — {closed} closed, {failed} failed.")

    finally:
        ctx.close()
        print("  Disconnected from OpenD.\n")


if __name__ == "__main__":
    main()
