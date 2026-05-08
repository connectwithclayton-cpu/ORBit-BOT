from __future__ import annotations

from enum import Enum

import pandas as pd

from fabio import indicators as ind
from fabio.settings import FabioBacktestSettings


class OpeningRangeStyle(str, Enum):
    RESEARCH = "research"  # 09:30-09:44 (5m aggregate)
    LIVE_MIRROR = "live_mirror"  # 09:30-09:40 (first 15m bucket on 5m data)


class DayRegime:
    """Per-symbol daily regime: gap, OR vs ATR, VIX tier risk, trend."""

    def __init__(
        self,
        cfg: FabioBacktestSettings,
        symbol: str,
        daily_slice: pd.DataFrame,
        intraday_slice: pd.DataFrame,
        vix: float,
        or_style: OpeningRangeStyle,
        session_open: float | None = None,
    ):
        self.cfg = cfg
        self.symbol = symbol
        self.vix = vix
        self.atr = ind.compute_atr(daily_slice)
        self.gap_pct = self._gap(daily_slice, session_open=session_open)

        if or_style == OpeningRangeStyle.RESEARCH:
            or_candles = intraday_slice.between_time("09:30", "09:44")
        else:
            or_candles = intraday_slice.between_time("09:30", "09:40")
        if or_candles.empty:
            or_candles = intraday_slice.iloc[:3]
        self.or_high = float(or_candles["High"].max())
        self.or_low = float(or_candles["Low"].min())
        self.or_width = self.or_high - self.or_low
        self.or_atr_pct = (self.or_width / self.atr * 100) if self.atr > 0 else 0

        c = daily_slice["Close"]
        self.bullish = (ind.ema(c, 10).iloc[-1] > ind.ema(c, 20).iloc[-1]) and (
            c.iloc[-1] > ind.ema(c, 50).iloc[-1]
        )

    def _gap(self, df: pd.DataFrame, session_open: float | None = None) -> float:
        if session_open is not None:
            if df.empty:
                return 0.0
            prev_close = float(df["Close"].iloc[-1])
            return abs((float(session_open) - prev_close) / prev_close) * 100

        if len(df) < 2:
            return 0.0
        return abs(
            (float(df["Open"].iloc[-1]) - float(df["Close"].iloc[-2]))
            / float(df["Close"].iloc[-2])
        ) * 100

    @property
    def vix_risk_pct(self) -> float:
        c = self.cfg
        if self.vix < c.vix_skip:
            return 0.0
        if self.vix <= c.vix_half_max:
            return c.risk_pct_half
        if self.vix <= c.vix_normal_max:
            return c.risk_pct_full
        if self.vix <= c.vix_aggressive_max:
            return c.risk_pct_aggressive
        return c.risk_pct_half

    @property
    def or_size_factor(self) -> float:
        c = self.cfg
        p = self.or_atr_pct
        if p < c.or_skip_pct_atr:
            return 0.0
        if p < c.or_normal_min_atr:
            return 0.75
        if p <= c.or_wide_pct_atr:
            return 1.0
        return 0.75

    @property
    def retest_required(self) -> bool:
        c = self.cfg
        return c.gap_retest_pct <= self.gap_pct < c.gap_skip_pct

    @property
    def tradeable(self) -> bool:
        c = self.cfg
        return (
            self.vix_risk_pct > 0
            and self.or_size_factor > 0
            and self.gap_pct < c.gap_skip_pct
        )

    def risk_multiplier(self, counter: bool = False, cb_mod: float = 1.0) -> float:
        c = self.cfg
        if counter:
            return 0.0
        return min(self.vix_risk_pct * self.or_size_factor * cb_mod, c.risk_pct_max)
