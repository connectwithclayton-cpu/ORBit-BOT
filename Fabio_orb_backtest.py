"""
Fabio Strategy Backtest Engine — CLI entrypoint.

Implementation lives in the `fabio` package (OO layout). This module keeps
backward-compatible names: SYMBOLS, DayRegime, load_data, run_backtest, etc.

Edit `DATA_SOURCE` below or use env FABIO_DATA_SOURCE / POLYGON_API_KEY.

Optional: set ``FABIO_BACKTEST_DEBUG_LOG`` to a file path for NDJSON timing lines (see ``fabio/backtest_instrumentation.py``); default is no debug file.
"""

from __future__ import annotations

import warnings
import time
from pathlib import Path

warnings.filterwarnings("ignore")

try:
    import yfinance as yf  # noqa: F401 — validated like legacy script
except ImportError:
    raise SystemExit("yfinance not found. Run: pip install yfinance pandas numpy scipy matplotlib requests")

# ─── Legacy toggle (applied when __main__ runs; reload cfg after changing) ───
DATA_SOURCE = "polygon"  # "polygon" | "yfinance"

from fabio.data_loader import FabioDataLoader
from fabio.engine import FabioBacktestEngine, BacktestMode
from fabio.options import black_scholes_call, black_scholes_put, option_price as _option_price_core
from fabio.regime import DayRegime as DayRegimeCore, OpeningRangeStyle
from fabio.reporting import compute_stats as _compute_stats_core, plot_results as _plot_results_core, print_summary as _print_summary_core
from fabio import indicators
from fabio import signals
from dataclasses import replace

from fabio.settings import FabioBacktestSettings
from fabio.backtest_instrumentation import log_backtest_debug
from fabio.run_outputs import resolve_output_paths, write_run_metadata

_cfg = FabioBacktestSettings.from_env()
_cfg.data_source = DATA_SOURCE

# ─── Module-level constants (backward compatible) ────────────────────────────
POLYGON_API_KEY = _cfg.polygon_api_key
SYMBOLS = _cfg.symbols
START_DATE = _cfg.start_date
END_DATE = _cfg.end_date
INITIAL_CAPITAL = _cfg.initial_capital

RISK_PCT_HALF = _cfg.risk_pct_half
RISK_PCT_FULL = _cfg.risk_pct_full
RISK_PCT_AGGRESSIVE = _cfg.risk_pct_aggressive
RISK_PCT_MAX = _cfg.risk_pct_max

VIX_SKIP = _cfg.vix_skip
VIX_HALF_MAX = _cfg.vix_half_max
VIX_NORMAL_MAX = _cfg.vix_normal_max
VIX_AGGRESSIVE_MAX = _cfg.vix_aggressive_max

GAP_SKIP_PCT = _cfg.gap_skip_pct
GAP_RETEST_PCT = _cfg.gap_retest_pct

OR_SKIP_PCT_ATR = _cfg.or_skip_pct_atr
OR_NORMAL_MIN_ATR = _cfg.or_normal_min_atr
OR_WIDE_PCT_ATR = _cfg.or_wide_pct_atr

CB_DAILY_LOSS_PCT = _cfg.cb_daily_loss_pct
CB_MAX_TRADES = _cfg.cb_max_trades
CB_MAX_LOSS_STREAK = _cfg.cb_max_loss_streak
CB_MAX_OPEN_POS = _cfg.cb_max_open_pos

TRIM_MULTIPLE = _cfg.trim_multiple
TRIM_PCT = _cfg.trim_pct
PROFIT_LOCK_MULTIPLE = _cfg.profit_lock_multiple

IV_BASE = _cfg.iv_base
OPTION_DTE = _cfg.option_dte
SLIPPAGE_PCT = _cfg.slippage_pct
COMMISSION = _cfg.commission


def ema(series, period: int):
    return indicators.ema(series, period)


def compute_atr(df, period: int = 14):
    return indicators.compute_atr(df, period)


def option_price(direction: str, S: float, T_days: float, iv=None):
    """Legacy signature; optional iv overrides settings iv_base."""
    c = _cfg if iv is None else replace(_cfg, iv_base=iv)
    return _option_price_core(direction, S, T_days, c)


class DayRegime(DayRegimeCore):
    """Same API as before: DayRegime(symbol, daily_slice, intraday_slice, vix)."""

    def __init__(self, symbol, daily_slice, intraday_slice, vix):
        super().__init__(
            _cfg, symbol, daily_slice, intraday_slice, vix, OpeningRangeStyle.RESEARCH
        )


def load_data(symbols, start, end):
    from dataclasses import replace

    c = replace(_cfg, symbols=list(symbols), start_date=start, end_date=end)
    return FabioDataLoader(c).load()


def check_entry(candles_5m, regime: DayRegimeCore):
    return signals.check_entry_research(candles_5m, regime)


def check_exit(candles, direction: str, regime: DayRegimeCore, candles_since_entry: int = 0):
    return signals.check_exit(candles, direction, regime, candles_since_entry=candles_since_entry)


def exit_timeframe(candles_5m, regime: DayRegimeCore) -> str:
    return "5m"


def run_backtest(data, vix_daily):
    eng = FabioBacktestEngine(_cfg)
    return eng.run(data, vix_daily, BacktestMode.RESEARCH)


def compute_stats(trades_df, equity_df):
    return _compute_stats_core(trades_df, equity_df, _cfg)


def print_summary(s):
    _print_summary_core(s, _cfg, title="FABIO STRATEGY BACKTEST RESULTS")


def plot_results(trades_df, equity_df, s, out_path="Fabio_backtest_report.png"):
    _plot_results_core(trades_df, equity_df, s, _cfg, out_path=out_path)


if __name__ == "__main__":
    t0 = time.time()
    _cfg.data_source = DATA_SOURCE
    log_backtest_debug(
        "H5",
        "Fabio_orb_backtest.py:__main__",
        "main_start",
        {
            "data_source": _cfg.data_source,
            "symbols": _cfg.symbols,
            "date_range": [_cfg.start_date, _cfg.end_date],
        },
        run_id="research",
    )

    print(
        f"\nFabio Strategy Backtest  |  {START_DATE} → {END_DATE}  |  Capital: ${INITIAL_CAPITAL:,.0f}\n"
    )

    t_load0 = time.time()
    data, vix = load_data(SYMBOLS, START_DATE, END_DATE)
    log_backtest_debug(
        "H6",
        "Fabio_orb_backtest.py:__main__",
        "data_loaded",
        {
            "load_seconds": round(time.time() - t_load0, 3),
            "symbols_loaded": list(data.keys()) if isinstance(data, dict) else [],
            "vix_rows": int(len(vix)) if hasattr(vix, "__len__") else -1,
        },
        run_id="research",
    )
    t_bt0 = time.time()
    trades_df, equity_df = run_backtest(data, vix)
    log_backtest_debug(
        "H6",
        "Fabio_orb_backtest.py:__main__",
        "backtest_completed",
        {
            "backtest_seconds": round(time.time() - t_bt0, 3),
            "trades_count": int(len(trades_df)),
            "equity_rows": int(len(equity_df)),
        },
        run_id="research",
    )

    s = compute_stats(trades_df, equity_df)
    log_backtest_debug(
        "H5",
        "Fabio_orb_backtest.py:__main__",
        "stats_computed",
        {
            "has_stats": bool(s),
            "total_pnl": float(s.get("total_pnl", 0.0)) if isinstance(s, dict) else 0.0,
            "total_return": float(s.get("total_return", 0.0)) if isinstance(s, dict) else 0.0,
            "elapsed_total_seconds": round(time.time() - t0, 3),
        },
        run_id="research",
    )
    print_summary(s)

    outputs = resolve_output_paths(
        Path(__file__).resolve().parent,
        "research",
        {
            "trades": "Fabio_backtest_trades.csv",
            "equity": "Fabio_backtest_equity.csv",
            "chart": "Fabio_backtest_report.png",
        },
    )
    trades_out = outputs.files["trades"]
    equity_out = outputs.files["equity"]
    chart_out = outputs.files["chart"]
    write_run_metadata(
        outputs.metadata,
        {
            "run_id": outputs.run_id,
            "runner": "Fabio_orb_backtest.py",
            "mode": "research",
            "data_source": _cfg.data_source,
            "vix_data_source": "yfinance",
            "start_date": _cfg.start_date,
            "end_date": _cfg.end_date,
            "symbols": _cfg.symbols,
            "diverted_from_root": outputs.diverted_from_root,
        },
    )
    if outputs.diverted_from_root:
        print(f"\n  Existing root outputs detected; writing this run to {outputs.output_dir}")

    trades_df.to_csv(trades_out, index=False)
    equity_df.to_csv(equity_out, index=False)

    if not trades_df.empty:
        plot_results(trades_df, equity_df, s, out_path=chart_out)
        print(f"\n  Trades  → {trades_out}")
        print(f"  Equity  → {equity_out}")
        print(f"  Chart   → {chart_out}\n")
    else:
        print("\n  No trades generated.\n")
