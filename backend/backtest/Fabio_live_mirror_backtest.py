"""
Legacy live-mirror backtest (older live-bot OR + entry approximation).

Uses ``BacktestMode.LIVE_MIRROR`` in ``backtest/fabio/engine.py`` — OR window **09:30–09:40 ET**
on 5m bars. Historical comparison only; research source of truth remains
``Fabio_orb_backtest.py``.

Run (from ``Fabio_bot/`` with ``PYTHONPATH=backend``):

    python backend/backtest/Fabio_live_mirror_backtest.py
"""

from __future__ import annotations

import sys
from pathlib import Path
import time

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from backtest import Fabio_orb_backtest as F
from backtest.fabio.backtest_instrumentation import log_backtest_debug
from backtest.fabio.data_loader import FabioDataLoader
from backtest.fabio.engine import BacktestMode, FabioBacktestEngine
from backtest.fabio.reporting import compute_stats, plot_results, print_summary
from backtest.fabio.run_outputs import resolve_output_paths, write_run_metadata
from fabio_bot_paths import fabio_bot_root

F._cfg.data_source = F.DATA_SOURCE


def main():
    t0 = time.time()
    log_backtest_debug(
        "H2",
        "Fabio_live_mirror_backtest.py:main",
        "main_start",
        {
            "data_source": F._cfg.data_source,
            "symbols": F._cfg.symbols,
            "date_range": [F._cfg.start_date, F._cfg.end_date],
        },
        run_id="legacy-live-mirror",
    )
    print(
        f"\nFabio legacy live-mirror backtest  |  {F.START_DATE} → {F.END_DATE}  "
        f"|  Capital: ${F.INITIAL_CAPITAL:,.0f}  |  Strategy cap: ${F._cfg.strategy_capital_cap:,.0f}\n"
    )
    print("  Rules: first-15m OR, live entry filter, research-risk sizing parity, profit-lock keeps ATR active.\n")

    loader = FabioDataLoader(F._cfg)
    t_load0 = time.time()
    data, vix = loader.load()
    log_backtest_debug(
        "H3",
        "Fabio_live_mirror_backtest.py:main",
        "data_loaded",
        {
            "load_seconds": round(time.time() - t_load0, 3),
            "symbols_loaded": list(data.keys()) if isinstance(data, dict) else [],
            "vix_rows": int(len(vix)) if hasattr(vix, "__len__") else -1,
        },
        run_id="legacy-live-mirror",
    )

    engine = FabioBacktestEngine(F._cfg)
    t_bt0 = time.time()
    trades_df, equity_df = engine.run(data, vix, BacktestMode.LIVE_MIRROR)
    log_backtest_debug(
        "H3",
        "Fabio_live_mirror_backtest.py:main",
        "backtest_completed",
        {
            "backtest_seconds": round(time.time() - t_bt0, 3),
            "trades_count": int(len(trades_df)),
            "equity_rows": int(len(equity_df)),
        },
        run_id="legacy-live-mirror",
    )

    s = compute_stats(trades_df, equity_df, F._cfg)
    log_backtest_debug(
        "H2",
        "Fabio_live_mirror_backtest.py:main",
        "stats_computed",
        {
            "has_stats": bool(s),
            "total_pnl": float(s.get("total_pnl", 0.0)) if isinstance(s, dict) else 0.0,
            "total_return": float(s.get("total_return", 0.0)) if isinstance(s, dict) else 0.0,
            "elapsed_total_seconds": round(time.time() - t0, 3),
        },
        run_id="legacy-live-mirror",
    )
    print_summary(s, F._cfg, title="FABIO LEGACY LIVE MIRROR (LIVE_MIRROR OR)")

    outputs = resolve_output_paths(
        fabio_bot_root(),
        "legacy_live_mirror",
        {
            "trades": "Fabio_live_mirror_trades.csv",
            "equity": "Fabio_live_mirror_equity.csv",
            "chart": "Fabio_live_mirror_report.png",
        },
    )
    trades_out = outputs.files["trades"]
    equity_out = outputs.files["equity"]
    chart_out = outputs.files["chart"]
    write_run_metadata(
        outputs.metadata,
        {
            "run_id": outputs.run_id,
            "runner": "Fabio_live_mirror_backtest.py",
            "mode": "legacy_live_mirror",
            "data_source": F._cfg.data_source,
            "vix_data_source": "yfinance",
            "start_date": F._cfg.start_date,
            "end_date": F._cfg.end_date,
            "symbols": F._cfg.symbols,
            "diverted_from_root": outputs.diverted_from_root,
        },
    )
    if outputs.diverted_from_root:
        print(f"\n  Existing root outputs detected; writing this run to {outputs.output_dir}")

    trades_df.to_csv(trades_out, index=False)
    equity_df.to_csv(equity_out, index=False)

    if not trades_df.empty:
        plot_results(
            trades_df,
            equity_df,
            s,
            F._cfg,
            out_path=chart_out,
            chart_title=(
                f"Fabio legacy live-mirror  ·  {F._cfg.start_date} → {F._cfg.end_date}  ·  "
                f"{' + '.join(F._cfg.symbols)}"
            ),
        )
        print(f"\n  Trades  → {trades_out}")
        print(f"  Equity  → {equity_out}")
        print(f"  Chart   → {chart_out}\n")
    else:
        print("\n  No trades generated.\n")


if __name__ == "__main__":
    main()
