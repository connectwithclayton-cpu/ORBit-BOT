"""Entry / exit signal logic for Fabio backtests."""

from __future__ import annotations

import pandas as pd

from . import indicators as ind
from .regime import DayRegime


def check_entry_research(candles_5m: pd.DataFrame, regime: DayRegime) -> str | None:
    if len(candles_5m) < 3:
        return None

    c1 = candles_5m.iloc[-2]
    c2 = candles_5m.iloc[-1]

    bull = (c1["Close"] > regime.or_high) and (c2["Close"] > regime.or_high)
    bear = (c1["Close"] < regime.or_low) and (c2["Close"] < regime.or_low)

    if not bull and not bear:
        return None

    if regime.retest_required and len(candles_5m) >= 4:
        prev = candles_5m.iloc[-3]
        tol = 0.005
        if bull and prev["Low"] > regime.or_high * (1 + tol):
            return None
        if bear and prev["High"] < regime.or_low * (1 - tol):
            return None

    if bull:
        return "CALL"
    if bear:
        return "PUT"
    return None


def check_entry_live_mirror(candles_5m: pd.DataFrame, regime: DayRegime) -> str | None:
    if len(candles_5m) < 3:
        return None

    c1 = candles_5m.iloc[-2]
    c2 = candles_5m.iloc[-1]
    or_high = regime.or_high
    or_low = regime.or_low

    bullish_break = (c1["Close"] > or_high) and (c2["Close"] > or_high)
    bearish_break = (c1["Close"] < or_low) and (c2["Close"] < or_low)

    if not bullish_break and not bearish_break:
        return None

    if bullish_break and float(c2["Low"]) < or_low:
        return None
    if bearish_break and float(c2["High"]) > or_high:
        return None

    if regime.retest_required and len(candles_5m) >= 4:
        prev = candles_5m.iloc[-3]
        tol = 0.005
        if bullish_break and float(prev["Low"]) > or_high * (1 + tol):
            return None
        if bearish_break and float(prev["High"]) < or_low * (1 - tol):
            return None

    if bullish_break:
        return "CALL"
    if bearish_break:
        return "PUT"
    return None


def check_exit(
    candles: pd.DataFrame,
    direction: str,
    regime: DayRegime,
    candles_since_entry: int = 0,
) -> bool:
    if candles.empty:
        return False

    or_mid = (regime.or_high + regime.or_low) / 2.0

    if len(candles) >= 2:
        c1 = float(candles["Close"].iloc[-2])
        c2 = float(candles["Close"].iloc[-1])
        if direction == "CALL" and c1 < or_mid and c2 < or_mid:
            return True
        if direction == "PUT" and c1 > or_mid and c2 > or_mid:
            return True

    if len(candles) >= 23:
        e10 = ind.ema(candles["Close"], 10)
        e20 = ind.ema(candles["Close"], 20)
        prev_diff = e10.iloc[-2] - e20.iloc[-2]
        curr_diff = e10.iloc[-1] - e20.iloc[-1]
        if direction == "CALL" and prev_diff > 0 and curr_diff <= 0:
            return True
        if direction == "PUT" and prev_diff < 0 and curr_diff >= 0:
            return True

    return False
