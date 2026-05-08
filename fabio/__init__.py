"""
Fabio backtest package — object-oriented core used by CLI scripts.

Typical usage::

    from fabio import FabioBacktestSettings, FabioDataLoader, FabioBacktestEngine, BacktestMode

    cfg = FabioBacktestSettings.from_env()
    loader = FabioDataLoader(cfg)
    data, vix = loader.load()
    engine = FabioBacktestEngine(cfg)
    trades, equity = engine.run(data, vix, BacktestMode.RESEARCH)
"""

from fabio.settings import FabioBacktestSettings
from fabio.data_loader import FabioDataLoader
from fabio.engine import FabioBacktestEngine, BacktestMode
from fabio.reporting import compute_stats, plot_results, print_summary

__all__ = [
    "FabioBacktestSettings",
    "FabioDataLoader",
    "FabioBacktestEngine",
    "BacktestMode",
    "compute_stats",
    "plot_results",
    "print_summary",
]
