"""Shared synthetic market data for Fabio strategy tests."""

from __future__ import annotations

import numpy as np
import pandas as pd

from backtest.fabio.settings import FabioBacktestSettings


def minimal_settings() -> FabioBacktestSettings:
    """Deterministic settings; avoid FabioBacktestSettings.from_env() in unit tests."""
    return FabioBacktestSettings()


def daily_bullish_atr(end_day: str = "2025-06-02", n: int = 60) -> pd.DataFrame:
    """Enough history for ATR(14) and EMA50; mild uptrend; tiny gap on last bar."""
    idx = pd.date_range(end=end_day, periods=n, freq="B", tz=None)
    close = 100.0 + np.linspace(0.0, 8.0, n)
    open_ = np.empty(n)
    open_[0] = close[0]
    open_[1:] = close[:-1] * 1.0001
    open_[-1] = close[-2] * 1.0002
    high = np.maximum(open_, close) * 1.002
    low = np.minimum(open_, close) * 0.998
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close},
        index=idx,
    )


def intraday_5m_or_known(
    day: str = "2025-06-02",
    or_high: float = 402.0,
    or_low: float = 398.0,
    post_or_flat: float = 400.0,
) -> pd.DataFrame:
    """
    Full regular session 5m bars (ET). OR window bars (09:30–09:40) set extrema;
    later bars flat at post_or_flat so OR high/low stay deterministic.
    """
    idx = pd.date_range(
        f"{day} 09:30",
        f"{day} 15:55",
        freq="5min",
        tz="America/New_York",
    )
    n = len(idx)
    o = np.full(n, post_or_flat)
    h = np.full(n, post_or_flat)
    l = np.full(n, post_or_flat)
    c = np.full(n, post_or_flat)

    times = idx.time
    t0930 = pd.Timestamp("09:30").time()
    t0935 = pd.Timestamp("09:35").time()
    t0940 = pd.Timestamp("09:40").time()

    for i, t in enumerate(times):
        if t == t0930:
            o[i], h[i], l[i], c[i] = 400.0, or_high, or_low + 0.5, 401.0
        elif t == t0935:
            o[i], h[i], l[i], c[i] = 401.0, or_high - 0.5, or_low, 400.5
        elif t == t0940:
            o[i], h[i], l[i], c[i] = 400.5, or_high, or_low, 399.5

    return pd.DataFrame(
        {"Open": o, "High": h, "Low": l, "Close": c, "volume": np.ones(n)},
        index=idx,
    )
