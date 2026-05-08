"""Live signal engine — ORB breakout and exit-timeframe helpers."""

from __future__ import annotations

import pandas as pd
from moomoo import KLType

from fabio_live.constants import EMA_GAP_TIGHT, EMA_GAP_WIDE
from fabio_live.market_data import ema
from fabio_live.regime import MarketRegime


class SignalEngine:
    """Detects ORB breakout on 5-min candles, manages exit signals."""

    def __init__(self, regime: MarketRegime):
        self.regime = regime

    def check_breakout(self, df_5m: pd.DataFrame) -> str | None:
        if len(df_5m) < 3:
            return None

        c1, c2 = df_5m.iloc[-2], df_5m.iloc[-1]
        or_high = self.regime.or_high
        or_low = self.regime.or_low

        bullish_break = (c1["close"] > or_high) and (c2["close"] > or_high)
        bearish_break = (c1["close"] < or_low) and (c2["close"] < or_low)

        if self.regime.retest_required:
            if len(df_5m) < 4:
                return None
            retest_candle = df_5m.iloc[-3]
            tolerance = 0.005
            if bullish_break and retest_candle["low"] > or_high * (1 + tolerance):
                return None
            if bearish_break and retest_candle["high"] < or_low * (1 - tolerance):
                return None

        if bullish_break:
            return "CALL"
        if bearish_break:
            return "PUT"
        return None

    def is_counter_trend(self, direction: str) -> bool:
        bull = self.regime.bullish_trend
        return (direction == "CALL" and not bull) or (direction == "PUT" and bull)

    def exit_timeframe(self, df_5m: pd.DataFrame) -> KLType:
        c = df_5m["close"]
        gap = abs(ema(c, 10).iloc[-1] - ema(c, 20).iloc[-1])
        ratio = gap / self.regime.atr if self.regime.atr > 0 else 0

        if ratio < EMA_GAP_TIGHT:
            return KLType.K_15M
        if ratio > EMA_GAP_WIDE:
            return KLType.K_3M
        return KLType.K_5M

    def check_ema_exit(self, df_exit: pd.DataFrame, direction: str) -> bool:
        c = df_exit["close"]
        last_close = c.iloc[-1]
        last_ema = ema(c, 10).iloc[-1]
        if direction == "CALL" and last_close < last_ema:
            return True
        if direction == "PUT" and last_close > last_ema:
            return True
        return False

    def check_or_reentry(self, df_5m: pd.DataFrame, direction: str) -> bool:
        last_close = df_5m["close"].iloc[-1]
        if direction == "CALL" and last_close < self.regime.or_high:
            return True
        if direction == "PUT" and last_close > self.regime.or_low:
            return True
        return False
