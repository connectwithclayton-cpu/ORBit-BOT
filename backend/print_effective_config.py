"""
print_effective_config.py — show resolved runtime config for live + backtests.

Run before market open / before starting the live bot (pre-flight).

If MOOMOO_TRADE_ENV resolves to REAL, prints a prominent warning banner first.

Usage:
    python3 print_effective_config.py
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict

from moomoo import TrdEnv

from fabio_bot_paths import fabio_bot_root

from config import (
    GOOGLE_CREDS_PATH,
    GOOGLE_SHEET_ID,
    MOOMOO_HOST,
    MOOMOO_PORT,
    MOOMOO_TRADE_ENV,
    TG_GROUP_ID,
    TG_PERSONAL_ID,
    TG_TOKEN,
)
from backtest.fabio.settings import FabioBacktestSettings


def _mask(value: str) -> str:
    if not value:
        return "(not set)"
    if len(value) <= 6:
        return "***"
    return f"{value[:2]}***{value[-2:]}"


def _print_real_trading_banner() -> None:
    raw = os.getenv("MOOMOO_TRADE_ENV", "SIMULATE").strip()
    bar = "!" * 72
    print()
    print(bar)
    print("  WARNING: MOOMOO_TRADE_ENV resolves to REAL (live) trading.")
    print("  Bot orders can execute against your real brokerage account.")
    print("  Confirm account, buying power, and risk limits before starting.")
    print(f"  Environment variable: MOOMOO_TRADE_ENV={raw!r}")
    print(bar)
    print()


def main() -> None:
    if MOOMOO_TRADE_ENV == TrdEnv.REAL:
        _print_real_trading_banner()

    cfg = FabioBacktestSettings.from_env()
    strategy = asdict(cfg)
    strategy["polygon_api_key"] = _mask(cfg.polygon_api_key)

    integrations = {
        "env_source": os.getenv("FABIO_ENV_FILE", str(fabio_bot_root() / ".env")),
        "moomoo_host": MOOMOO_HOST,
        "moomoo_port": MOOMOO_PORT,
        "moomoo_trade_env": str(MOOMOO_TRADE_ENV),
        "telegram_token": _mask(TG_TOKEN),
        "telegram_personal_chat_id": _mask(TG_PERSONAL_ID),
        "telegram_group_chat_id": _mask(TG_GROUP_ID),
        "google_sheet_id": _mask(GOOGLE_SHEET_ID),
        "google_creds_path": GOOGLE_CREDS_PATH or "(not set)",
    }

    print("Fabio effective runtime config")
    print("=" * 36)
    print("\n[Strategy settings (fabio/settings.py)]")
    print(json.dumps(strategy, indent=2, sort_keys=True))
    print("\n[Integrations (config.py)]")
    print(json.dumps(integrations, indent=2, sort_keys=True))

    print("\n[Sanity summary]")
    print(f"- symbols: {strategy['symbols']}")
    print(
        f"- VIX tiers: skip<{strategy['vix_skip']} / half<={strategy['vix_half_max']} / "
        f"normal<={strategy['vix_normal_max']} / aggressive<={strategy['vix_aggressive_max']}"
    )
    print(
        f"- risk caps: full={strategy['risk_pct_full']:.2f}, half={strategy['risk_pct_half']:.2f}, "
        f"max={strategy['risk_pct_max']:.2f}"
    )
    print(
        f"- sizing base: min(portfolio, strategy_capital_cap * "
        f"research_risk_capital_multiplier) = min(portfolio, {strategy['strategy_capital_cap']:.0f} * "
        f"{strategy['research_risk_capital_multiplier']:.2f})"
    )
    if MOOMOO_TRADE_ENV == TrdEnv.REAL:
        print("- Moomoo: REAL — live orders enabled (not paper / simulate).")
    else:
        print("- Moomoo: SIMULATE — paper-style environment (set MOOMOO_TRADE_ENV=REAL only deliberately).")


if __name__ == "__main__":
    main()

