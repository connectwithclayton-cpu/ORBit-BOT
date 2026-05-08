from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from fabio.engine import BacktestMode, FabioBacktestEngine
from fabio.reporting import compute_stats
from fabio.run_outputs import resolve_output_paths, write_run_metadata
from fabio.settings import FabioBacktestSettings


def _daily_with_current_session(day: str = "2026-05-07") -> pd.DataFrame:
    idx = pd.date_range(end=day, periods=25, freq="B")
    close = np.linspace(100.0, 124.0, len(idx))
    open_ = close.copy()
    open_[-1] = 500.0
    return pd.DataFrame(
        {
            "Open": open_,
            "High": close + 1.0,
            "Low": close - 1.0,
            "Close": close,
        },
        index=idx,
    )


def _intraday_5m(day: str = "2026-05-07") -> pd.DataFrame:
    idx = pd.date_range(f"{day} 09:30", f"{day} 15:55", freq="5min")
    close = np.full(len(idx), 100.0)
    return pd.DataFrame(
        {
            "Open": close,
            "High": close + 0.5,
            "Low": close - 0.5,
            "Close": close,
        },
        index=idx,
    )


def _intraday_3m(day: str = "2026-05-07") -> pd.DataFrame:
    idx = pd.date_range(f"{day} 10:00", f"{day} 15:45", freq="3min")
    close = np.full(len(idx), 100.1)
    return pd.DataFrame(
        {
            "Open": close,
            "High": close + 0.1,
            "Low": close - 0.1,
            "Close": close,
        },
        index=idx,
    )


def test_engine_uses_prior_daily_and_prior_vix_for_intraday_decisions(monkeypatch):
    from fabio import engine as eng

    seen: dict[str, object] = {}

    class SpyRegime:
        def __init__(self, _cfg, _symbol, daily_slice, _intraday_slice, vix, _or_style, session_open=None):
            seen["max_daily_date"] = daily_slice.index.max().date()
            seen["vix"] = vix
            seen["session_open"] = session_open
            self.tradeable = True
            self.bullish = True
            self.vix = vix
            self.atr = 10.0
            self.or_high = 101.0
            self.or_low = 99.0
            self.or_atr_pct = 20.0
            self.gap_pct = 0.1

        def risk_multiplier(self, counter: bool, cb_mod: float) -> float:
            return 0.1

    monkeypatch.setattr(eng, "DayRegime", SpyRegime)
    monkeypatch.setattr(eng, "option_price", lambda *_args, **_kwargs: 1.0)
    monkeypatch.setattr(eng.signals, "check_entry_research", lambda candles, regime: "CALL")
    monkeypatch.setattr(eng.signals, "check_exit", lambda *args, **kwargs: False)

    cfg = FabioBacktestSettings(symbols=["SPY"])
    data = {
        "SPY": {
            "daily": _daily_with_current_session(),
            "intraday": _intraday_5m(),
            "intraday_3m": _intraday_3m(),
        }
    }
    vix = pd.DataFrame(
        {"Close": [18.0, 29.0]},
        index=[pd.Timestamp("2026-05-06"), pd.Timestamp("2026-05-07")],
    )

    trades, _ = FabioBacktestEngine(cfg).run(data, vix, BacktestMode.RESEARCH)

    assert not trades.empty
    assert seen["max_daily_date"] == pd.Timestamp("2026-05-06").date()
    assert seen["vix"] == 18.0
    assert seen["session_open"] == pytest.approx(500.0)
    assert trades.iloc[0]["vix"] == 18.0
    assert trades.iloc[0]["exit_tf"] == "3m"


def test_profit_factor_uses_gross_profit_over_gross_loss():
    trades = pd.DataFrame(
        {
            "total_pnl": [100.0, 100.0, -50.0],
            "exit_reason": ["EOD", "EOD", "Strategy exit"],
            "direction": ["CALL", "PUT", "CALL"],
            "counter_trend": [False, False, False],
            "symbol": ["SPY", "QQQ", "NVDA"],
        }
    )
    equity = pd.DataFrame(
        {
            "date": ["2026-05-05", "2026-05-06", "2026-05-07"],
            "capital": [10100.0, 10200.0, 10150.0],
            "day_pnl": [100.0, 100.0, -50.0],
        }
    )

    stats = compute_stats(trades, equity, FabioBacktestSettings())

    assert stats["profit_factor"] == pytest.approx(4.0)


def test_existing_root_outputs_are_diverted_to_run_directory(tmp_path: Path):
    (tmp_path / "Fabio_backtest_trades.csv").write_text("baseline\n", encoding="utf-8")

    outputs = resolve_output_paths(
        tmp_path,
        "research",
        {
            "trades": "Fabio_backtest_trades.csv",
            "equity": "Fabio_backtest_equity.csv",
        },
    )

    assert outputs.diverted_from_root is True
    assert outputs.output_dir != tmp_path
    assert outputs.files["trades"].parent == outputs.output_dir
    assert (tmp_path / "Fabio_backtest_trades.csv").read_text(encoding="utf-8") == "baseline\n"

    write_run_metadata(outputs.metadata, {"run_id": outputs.run_id, "ok": True})
    assert outputs.metadata.exists()


def test_open_position_cap_blocks_overlapping_entries(monkeypatch):
    from fabio import engine as eng

    class TradeableRegime:
        def __init__(self, _cfg, symbol, *_args, **_kwargs):
            self.symbol = symbol
            self.tradeable = True
            self.bullish = True
            self.vix = 18.0
            self.atr = 100.0
            self.or_high = 101.0
            self.or_low = 99.0
            self.or_atr_pct = 20.0
            self.gap_pct = 0.1

        def risk_multiplier(self, counter: bool, cb_mod: float) -> float:
            return 0.1

    monkeypatch.setattr(eng, "DayRegime", TradeableRegime)
    monkeypatch.setattr(eng, "option_price", lambda *_args, **_kwargs: 1.0)
    monkeypatch.setattr(
        eng.signals,
        "check_entry_research",
        lambda candles, regime: "CALL" if len(candles) >= 3 else None,
    )
    monkeypatch.setattr(eng.signals, "check_exit", lambda *args, **kwargs: False)

    cfg = FabioBacktestSettings(symbols=["SPY", "QQQ"], cb_max_open_pos=1)
    data = {
        sym: {
            "daily": _daily_with_current_session(),
            "intraday": _intraday_5m(),
            "intraday_3m": _intraday_3m(),
        }
        for sym in cfg.symbols
    }
    vix = pd.DataFrame({"Close": [18.0]}, index=[pd.Timestamp("2026-05-06")])

    trades, _ = FabioBacktestEngine(cfg).run(data, vix, BacktestMode.RESEARCH)

    assert len(trades) == 1
    assert trades.iloc[0]["symbol"] == "SPY"


def test_later_entry_sizing_uses_earlier_same_day_realized_pnl(monkeypatch):
    from fabio import engine as eng

    class TradeableRegime:
        def __init__(self, _cfg, symbol, *_args, **_kwargs):
            self.symbol = symbol
            self.tradeable = True
            self.bullish = True
            self.vix = 18.0
            self.atr = 100.0
            self.or_high = 101.0
            self.or_low = 99.0
            self.or_atr_pct = 20.0
            self.gap_pct = 0.1

        def risk_multiplier(self, counter: bool, cb_mod: float) -> float:
            return 0.1

    def entry_by_symbol_and_time(candles, regime):
        last_ts = pd.Timestamp(candles.index[-1])
        if regime.symbol == "SPY" and last_ts >= pd.Timestamp("2026-05-07 09:55"):
            return "CALL"
        if regime.symbol == "QQQ" and last_ts >= pd.Timestamp("2026-05-07 10:05"):
            return "CALL"
        return None

    def exit_spy_at_1000(candles, _direction, regime, **_kwargs):
        last_ts = pd.Timestamp(candles.index[-1])
        return regime.symbol == "SPY" and last_ts >= pd.Timestamp("2026-05-07 10:00")

    def exit_bars(sym: str) -> pd.DataFrame:
        df = _intraday_3m()
        if sym == "SPY":
            df.loc[pd.Timestamp("2026-05-07 10:00"), "Close"] = 120.0
        return df

    monkeypatch.setattr(eng, "DayRegime", TradeableRegime)
    monkeypatch.setattr(eng, "option_price", lambda *_args, **_kwargs: 1.0)
    monkeypatch.setattr(eng.signals, "check_entry_research", entry_by_symbol_and_time)
    monkeypatch.setattr(eng.signals, "check_exit", exit_spy_at_1000)

    cfg = FabioBacktestSettings(
        symbols=["SPY", "QQQ"],
        initial_capital=5_000.0,
        profit_lock_multiple=999.0,
    )
    data = {
        sym: {
            "daily": _daily_with_current_session(),
            "intraday": _intraday_5m(),
            "intraday_3m": exit_bars(sym),
        }
        for sym in cfg.symbols
    }
    vix = pd.DataFrame({"Close": [18.0]}, index=[pd.Timestamp("2026-05-06")])

    trades, _ = FabioBacktestEngine(cfg).run(data, vix, BacktestMode.RESEARCH)

    spy = trades[trades["symbol"] == "SPY"].iloc[0]
    qqq = trades[trades["symbol"] == "QQQ"].iloc[0]
    assert spy["exit_time"] < qqq["entry_time"]
    assert int(qqq["n_contracts"]) == 9
