"""
config.py — integrations and credentials only.

Strategy/risk parameters live in `backtest/fabio/settings.py` (FabioBacktestSettings),
which is shared by backtests and live bot logic.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
import moomoo as ft

from fabio_bot_paths import fabio_bot_root

_DEFAULT_ENV_PATH = fabio_bot_root() / ".env"
_ENV_OVERRIDE = os.getenv("FABIO_ENV_FILE", "").strip()
if _ENV_OVERRIDE:
    load_dotenv(_ENV_OVERRIDE)
else:
    load_dotenv(_DEFAULT_ENV_PATH)

# ── Moomoo connection ─────────────────────────────────────────────────────────
MOOMOO_HOST = os.getenv("MOOMOO_HOST", "127.0.0.1")
MOOMOO_PORT = int(os.getenv("MOOMOO_PORT", "11111"))
_env = os.getenv("MOOMOO_TRADE_ENV", "SIMULATE").upper()
MOOMOO_TRADE_ENV = ft.TrdEnv.REAL if _env == "REAL" else ft.TrdEnv.SIMULATE

# Modeled equity (SIMULATE ONLY by default — maps Moomoo total_assets to a $10k test book).
# modeled = FABIO_DISPLAY_EQUITY_START + (raw_total_assets - FABIO_MOOMOO_REFERENCE_EQUITY)
FABIO_MOOMOO_REFERENCE_EQUITY = float(os.getenv("FABIO_MOOMOO_REFERENCE_EQUITY", "1000000"))
FABIO_DISPLAY_EQUITY_START = float(os.getenv("FABIO_DISPLAY_EQUITY_START", "10000"))
_fabio_modeled_raw = os.getenv("FABIO_MODELED_EQUITY_ENABLED", "").strip().lower()
if _fabio_modeled_raw == "1":
    FABIO_MODELED_EQUITY_ENABLED = True
elif _fabio_modeled_raw == "0":
    FABIO_MODELED_EQUITY_ENABLED = False
else:
    FABIO_MODELED_EQUITY_ENABLED = MOOMOO_TRADE_ENV != ft.TrdEnv.REAL


def modeled_equity_annotation_suffix() -> str:
    """Short suffix for Sheets / logs when modeled paper equity is enabled."""
    if not FABIO_MODELED_EQUITY_ENABLED:
        return ""
    return (
        " | Modeled book "
        f"${FABIO_DISPLAY_EQUITY_START:,.0f} (Moomoo ref ${FABIO_MOOMOO_REFERENCE_EQUITY:,.0f})"
    )


def modeled_equity_dashboard_subtitle() -> str | None:
    """One-line subtitle for dashboard HTML when modeling is enabled; else None."""
    if not FABIO_MODELED_EQUITY_ENABLED:
        return None
    return (
        f"Paper equity modeled ${FABIO_DISPLAY_EQUITY_START:,.0f} "
        f"vs broker ref ${FABIO_MOOMOO_REFERENCE_EQUITY:,.0f}. "
        "Per-trade dollar P&Ls are unchanged."
    )


# Backward-compat aliases for any old imports
HOST = MOOMOO_HOST
PORT = MOOMOO_PORT
TRADE_ENV = MOOMOO_TRADE_ENV

# ── Telegram ──────────────────────────────────────────────────────────────────
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_PERSONAL_ID = os.getenv("TELEGRAM_PERSONAL_CHAT_ID", "")
TG_GROUP_ID = os.getenv("TELEGRAM_GROUP_CHAT_ID", "")
TG_STOP_CONFIRM_CODE = os.getenv("TELEGRAM_STOP_CONFIRM_CODE", "")

# ── Optional Google Sheets integration env hints ─────────────────────────────
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")
GOOGLE_CREDS_PATH = os.getenv("GOOGLE_CREDS_PATH", "")
