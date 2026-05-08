"""Regression: profit-lock behavior stays aligned across backtest modes."""

from __future__ import annotations

import numpy as np
import pandas as pd

from fabio.engine import BacktestMode, FabioBacktestEngine
from fabio.settings import FabioBacktestSettings


class _StubRegime:
    def __init__(self, *args, **kwargs):
        self.tradeable = True
        self.bullish = True
        self.vix = 18.0
        self.atr = 0.5
        self.or_high = 101.0
        self.or_low = 99.0
        self.or_atr_pct = 20.0
        self.gap_pct = 0.1

    def risk_multiplier(self, counter: bool, cb_mod: float) -> float:
        return 0.1


def _make_daily(n: int = 30) -> pd.DataFrame:
    idx = pd.date_range(end="2026-05-07", periods=n, freq="B")
    close = np.linspace(100.0, 110.0, n)
    return pd.DataFrame(
        {
            "Open": close,
            "High": close + 1.0,
            "Low": close - 1.0,
            "Close": close,
        },
        index=idx,
    )


def _make_intraday_5m(day: str = "2026-05-07") -> pd.DataFrame:
    idx = pd.date_range(f"{day} 09:30", f"{day} 15:55", freq="5min")
    close = np.full(len(idx), 100.0)
    return pd.DataFrame(
        {
            "Open": close,
            "High": close + 0.1,
            "Low": close - 0.1,
            "Close": close,
        },
        index=idx,
    )


def _make_intraday_3m(day: str = "2026-05-07") -> pd.DataFrame:
    # Entry occurs at ~09:55 from entry stub; then:
    # 09:57 locks profits (close=100.3), 10:00 breaches 2xATR stop (close=98.8).
    idx = pd.to_datetime(
        [
            f"{day} 09:57",
            f"{day} 10:00",
            f"{day} 15:45",
        ]
    )
    return pd.DataFrame(
        {
            "Open": [100.3, 98.8, 98.7],
            "High": [100.4, 98.9, 98.8],
            "Low": [100.2, 98.7, 98.6],
            "Close": [100.3, 98.8, 98.7],
        },
        index=idx,
    )


def test_profit_lock_keeps_atr_active_in_both_modes(monkeypatch):
    from fabio import engine as eng

    monkeypatch.setattr(eng, "DayRegime", _StubRegime)
    monkeypatch.setattr(eng, "option_price", lambda *_args, **_kwargs: 1.0)
    monkeypatch.setattr(
        eng.signals,
        "check_entry_research",
        lambda candles, regime: "CALL" if len(candles) >= 3 else None,
    )
    monkeypatch.setattr(
        eng.signals,
        "check_entry_live_mirror",
        lambda candles, regime: "CALL" if len(candles) >= 3 else None,
    )
    # If strategy-exit runs after lock, this would force wrong reason.
    monkeypatch.setattr(eng.signals, "check_exit", lambda *args, **kwargs: True)

    cfg = FabioBacktestSettings(symbols=["SPY"])
    bt = FabioBacktestEngine(cfg)
    data = {
        "SPY": {
            "daily": _make_daily(),
            "intraday": _make_intraday_5m(),
            "intraday_3m": _make_intraday_3m(),
        }
    }
    vix = pd.DataFrame({"Close": [18.0]}, index=[pd.Timestamp("2026-05-07")])

    t_research, _ = bt.run(data, vix, BacktestMode.RESEARCH)
    t_live, _ = bt.run(data, vix, BacktestMode.LIVE_MIRROR)

    assert not t_research.empty
    assert not t_live.empty
    assert t_research.iloc[0]["exit_reason"] == "Hard Stop 2×ATR"
    assert t_live.iloc[0]["exit_reason"] == "Hard Stop 2xATR"


def test_position_sizing_matches_research_risk_base_in_both_modes(monkeypatch):
    from fabio import engine as eng

    monkeypatch.setattr(eng, "DayRegime", _StubRegime)
    monkeypatch.setattr(eng, "option_price", lambda *_args, **_kwargs: 1.0)
    monkeypatch.setattr(
        eng.signals,
        "check_entry_research",
        lambda candles, regime: "CALL" if len(candles) >= 3 else None,
    )
    monkeypatch.setattr(
        eng.signals,
        "check_entry_live_mirror",
        lambda candles, regime: "CALL" if len(candles) >= 3 else None,
    )
    monkeypatch.setattr(eng.signals, "check_exit", lambda *args, **kwargs: False)

    cfg = FabioBacktestSettings(symbols=["SPY"], initial_capital=50_000.0)
    bt = FabioBacktestEngine(cfg)
    data = {
        "SPY": {
            "daily": _make_daily(),
            "intraday": _make_intraday_5m(),
            "intraday_3m": _make_intraday_3m(),
        }
    }
    vix = pd.DataFrame({"Close": [18.0]}, index=[pd.Timestamp("2026-05-07")])

    t_research, _ = bt.run(data, vix, BacktestMode.RESEARCH)
    t_live, _ = bt.run(data, vix, BacktestMode.LIVE_MIRROR)

    assert not t_research.empty
    assert not t_live.empty
    assert int(t_research.iloc[0]["n_contracts"]) == int(t_live.iloc[0]["n_contracts"])
    assert int(t_research.iloc[0]["n_contracts"]) == 49
