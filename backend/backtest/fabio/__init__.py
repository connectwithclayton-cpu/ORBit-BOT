"""
Fabio backtest package — object-oriented core used by CLI scripts under ``backtest/``.

Typical usage::

    from backtest.fabio import FabioBacktestSettings, FabioDataLoader, FabioBacktestEngine, BacktestMode

    cfg = FabioBacktestSettings.from_env()
    loader = FabioDataLoader(cfg)
    data, vix = loader.load()
    engine = FabioBacktestEngine(cfg)
    trades, equity = engine.run(data, vix, BacktestMode.RESEARCH)
"""

from .data_loader import FabioDataLoader
from .engine import BacktestMode, FabioBacktestEngine
from .reporting import compute_stats, plot_results, print_summary
from .settings import FabioBacktestSettings

__all__ = [
    "FabioBacktestSettings",
    "FabioDataLoader",
    "FabioBacktestEngine",
    "BacktestMode",
    "compute_stats",
    "plot_results",
    "print_summary",
]
