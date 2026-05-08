"""Golden-path entry (CALL) and midpoint exit on synthetic bars."""

from __future__ import annotations

import pandas as pd

from fabio.regime import DayRegime, OpeningRangeStyle
from fabio.signals import check_entry_research, check_exit

from tests.conftest import daily_bullish_atr, intraday_5m_or_known, minimal_settings


def _intraday_with_call_breakout(day: str = "2025-06-02") -> pd.DataFrame:
    """OR 398–402; two consecutive 5m closes above OR high at 10:00 and 10:05."""
    or_high, or_low = 402.0, 398.0
    df = intraday_5m_or_known(day=day, or_high=or_high, or_low=or_low)
    df = df.copy()
    m1000 = (df.index.hour == 10) & (df.index.minute == 0)
    m1005 = (df.index.hour == 10) & (df.index.minute == 5)
    df.loc[m1000, ["Open", "High", "Low", "Close"]] = [
        402.4,
        403.4,
        402.3,
        403.0,
    ]
    df.loc[m1005, ["Open", "High", "Low", "Close"]] = [
        403.0,
        403.3,
        402.9,
        403.1,
    ]
    return df


def test_golden_call_entry_two_closes_above_or_high() -> None:
    cfg = minimal_settings()
    day = "2025-06-02"
    daily = daily_bullish_atr(end_day=day)
    intraday = _intraday_with_call_breakout(day=day)
    regime = DayRegime(
        cfg, "SPY", daily, intraday, vix=18.0, or_style=OpeningRangeStyle.RESEARCH
    )
    assert regime.tradeable
    assert not regime.retest_required

    ts_1005 = pd.Timestamp(f"{day} 10:05", tz="America/New_York")
    window = intraday.loc[intraday.index <= ts_1005]

    sig = check_entry_research(window, regime)
    assert sig == "CALL"


def test_golden_call_exit_two_closes_below_or_midpoint() -> None:
    cfg = minimal_settings()
    day = "2025-06-02"
    daily = daily_bullish_atr(end_day=day)
    intraday = _intraday_with_call_breakout(day=day)
    regime = DayRegime(
        cfg, "SPY", daily, intraday, vix=18.0, or_style=OpeningRangeStyle.RESEARCH
    )

    or_mid = (regime.or_high + regime.or_low) / 2.0
    assert or_mid == 400.0

    exit_bars = pd.DataFrame(
        {
            "Open": [401.0, 399.5, 398.0],
            "High": [401.5, 400.0, 398.5],
            "Low": [400.0, 399.0, 397.5],
            "Close": [401.0, 399.0, 397.5],
        }
    )

    assert float(exit_bars["Close"].iloc[-2]) < or_mid
    assert float(exit_bars["Close"].iloc[-1]) < or_mid
    assert check_exit(exit_bars, "CALL", regime) is True


def test_golden_put_entry_two_closes_below_or_low() -> None:
    cfg = minimal_settings()
    day = "2025-06-02"
    or_high, or_low = 402.0, 398.0
    daily = daily_bullish_atr(end_day=day)
    intraday = intraday_5m_or_known(day=day, or_high=or_high, or_low=or_low)
    intraday = intraday.copy()
    m1000 = (intraday.index.hour == 10) & (intraday.index.minute == 0)
    m1005 = (intraday.index.hour == 10) & (intraday.index.minute == 5)
    intraday.loc[m1000, ["Open", "High", "Low", "Close"]] = [398.5, 399.0, 397.0, 397.5]
    intraday.loc[m1005, ["Open", "High", "Low", "Close"]] = [397.5, 397.8, 396.5, 397.0]

    regime = DayRegime(
        cfg, "SPY", daily, intraday, vix=18.0, or_style=OpeningRangeStyle.RESEARCH
    )
    assert regime.tradeable

    ts_1005 = pd.Timestamp(f"{day} 10:05", tz="America/New_York")
    window = intraday.loc[intraday.index <= ts_1005]
    assert check_entry_research(window, regime) == "PUT"
