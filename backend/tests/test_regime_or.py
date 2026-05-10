"""DayRegime opening range bounds on synthetic 5m data."""

from __future__ import annotations

from backtest.fabio.regime import DayRegime, OpeningRangeStyle

from tests.conftest import daily_bullish_atr, intraday_5m_or_known, minimal_settings


def test_day_regime_research_or_high_low_matches_or_window_extrema() -> None:
    cfg = minimal_settings()
    day = "2025-06-02"
    or_high, or_low = 402.0, 398.0
    daily = daily_bullish_atr(end_day=day)
    intraday = intraday_5m_or_known(day=day, or_high=or_high, or_low=or_low)

    regime = DayRegime(
        cfg, "SPY", daily, intraday, vix=18.0, or_style=OpeningRangeStyle.RESEARCH
    )

    assert regime.or_high == or_high
    assert regime.or_low == or_low
    assert regime.or_width == or_high - or_low


def test_day_regime_tradeable_when_vix_gap_and_or_width_ok() -> None:
    cfg = minimal_settings()
    day = "2025-06-02"
    daily = daily_bullish_atr(end_day=day)
    intraday = intraday_5m_or_known(day=day, or_high=402.0, or_low=398.0)

    regime = DayRegime(
        cfg, "SPY", daily, intraday, vix=18.0, or_style=OpeningRangeStyle.RESEARCH
    )

    assert regime.vix_risk_pct > 0
    assert regime.or_size_factor > 0
    assert regime.gap_pct < cfg.gap_skip_pct
    assert regime.tradeable


def test_day_regime_live_mirror_or_uses_0930_0940_window() -> None:
    """OR from 09:30–09:40 on 5m bars; same three bars as research for this schedule."""
    cfg = minimal_settings()
    day = "2025-06-02"
    or_high, or_low = 405.0, 397.0
    daily = daily_bullish_atr(end_day=day)
    intraday = intraday_5m_or_known(day=day, or_high=or_high, or_low=or_low)

    regime = DayRegime(
        cfg, "SPY", daily, intraday, vix=18.0, or_style=OpeningRangeStyle.LIVE_MIRROR
    )

    or_candles = intraday.between_time("09:30", "09:40")
    assert not or_candles.empty
    assert regime.or_high == float(or_candles["High"].max())
    assert regime.or_low == float(or_candles["Low"].min())
