"""Live MarketRegime — VIX tiers, gap, OR quality, trend (aligned to research backtest)."""

from __future__ import annotations

import pandas as pd

from fabio_live.constants import (
    GAP_RETEST_PCT,
    GAP_SKIP_PCT,
    OR_NORMAL_MIN_ATR,
    OR_SKIP_PCT_ATR,
    OR_WIDE_PCT_ATR,
    RISK_PCT_FULL,
    RISK_PCT_HALF,
    RISK_PCT_MAX,
    VIX_AGGRESSIVE_MAX,
    VIX_HALF_MAX,
    VIX_NORMAL_MAX,
    VIX_SKIP,
)
from fabio_live.market_data import compute_atr, ema


class MarketRegime:
    """
    Classifies each symbol's day using ORBIT VIX tiers, gap filter, and
    OR quality thresholds. Retains CJ's binary EMA trend scoring.

    Opening range matches Fabio_orb_backtest (research): max high / min low of
    5-minute bars from 09:30–09:44 ET (not the first 15m candle alone).
    """

    def __init__(
        self, symbol: str, df_daily: pd.DataFrame, df_5m: pd.DataFrame, vix: float
    ):
        self.symbol = symbol
        self.vix = vix
        self.atr = compute_atr(df_daily)
        self.gap_pct = self._gap(df_daily)
        self.or_high, self.or_low = self._opening_range_from_5m(df_5m)
        self.or_width = self.or_high - self.or_low
        self.or_atr_pct = (self.or_width / self.atr) * 100 if self.atr > 0 else 0

        c = df_daily["close"]
        self.ema10 = ema(c, 10).iloc[-1]
        self.ema20 = ema(c, 20).iloc[-1]
        self.ema50 = ema(c, 50).iloc[-1]
        self.bullish_trend = (self.ema10 > self.ema20) and (c.iloc[-1] > self.ema50)

    def _gap(self, df_daily: pd.DataFrame) -> float:
        if len(df_daily) < 2:
            return 0.0
        prev_close = df_daily["close"].iloc[-2]
        today_open = df_daily["open"].iloc[-1]
        return abs((today_open - prev_close) / prev_close) * 100

    def _opening_range_from_5m(self, df_5m: pd.DataFrame) -> tuple[float, float]:
        """Match Fabio_orb_backtest DayRegime: 09:30–09:44 on 5m bars."""
        if df_5m.empty:
            return 0.0, 0.0
        tmp = df_5m.copy()
        tmp.index = pd.to_datetime(tmp["time_key"])
        or_candles = tmp.between_time("09:30", "09:44")
        if or_candles.empty:
            or_candles = tmp.iloc[:3]
        return float(or_candles["high"].max()), float(or_candles["low"].min())

    @property
    def vix_risk_pct(self) -> float:
        if self.vix < VIX_SKIP:
            return 0.0
        if self.vix <= VIX_HALF_MAX:
            return RISK_PCT_HALF
        if self.vix <= VIX_NORMAL_MAX:
            return RISK_PCT_FULL
        if self.vix <= VIX_AGGRESSIVE_MAX:
            return RISK_PCT_FULL
        return RISK_PCT_HALF

    @property
    def vix_label(self) -> str:
        if self.vix < VIX_SKIP:
            return f"SKIP(<{VIX_SKIP})"
        if self.vix <= VIX_HALF_MAX:
            return f"HALF({VIX_SKIP}-{VIX_HALF_MAX})"
        if self.vix <= VIX_NORMAL_MAX:
            return f"NORMAL({VIX_HALF_MAX}-{VIX_NORMAL_MAX})"
        if self.vix <= VIX_AGGRESSIVE_MAX:
            return f"AGGRESSIVE({VIX_NORMAL_MAX}-{VIX_AGGRESSIVE_MAX})"
        return f"HALF(>{VIX_AGGRESSIVE_MAX})"

    @property
    def or_size_factor(self) -> float:
        if self.or_atr_pct < OR_SKIP_PCT_ATR:
            return 0.0
        if self.or_atr_pct < OR_NORMAL_MIN_ATR:
            return 0.75
        if self.or_atr_pct <= OR_WIDE_PCT_ATR:
            return 1.0
        return 0.75

    @property
    def retest_required(self) -> bool:
        return GAP_RETEST_PCT <= self.gap_pct < GAP_SKIP_PCT

    @property
    def tradeable(self) -> bool:
        return (
            self.vix_risk_pct > 0
            and self.or_size_factor > 0
            and self.gap_pct < GAP_SKIP_PCT
        )

    def risk_multiplier(
        self, counter_trend: bool = False, cb_modifier: float = 1.0
    ) -> float:
        if counter_trend:
            return 0.0
        base = self.vix_risk_pct * self.or_size_factor
        return min(base * cb_modifier, RISK_PCT_MAX)

    @property
    def day_color(self) -> str:
        if not self.tradeable:
            return "RED"
        if self.vix_risk_pct >= RISK_PCT_FULL and self.or_size_factor == 1.0:
            return "GREEN"
        return "YELLOW"

    def summary(self) -> str:
        retest_tag = " | RETEST REQ'D" if self.retest_required else ""
        return (
            f"[{self.symbol}] Day={self.day_color} | VIX={self.vix:.1f} ({self.vix_label}) | "
            f"OR={self.or_width:.2f} ({self.or_atr_pct:.0f}% ATR, ×{self.or_size_factor:.2f}) | "
            f"Gap={self.gap_pct:.2f}%{retest_tag} | "
            f"Trend={'BULL' if self.bullish_trend else 'BEAR'}"
        )
