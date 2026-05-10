"""Moomoo + yfinance market data helpers for the live bot."""

from __future__ import annotations

import time
from zoneinfo import ZoneInfo

import pandas as pd
from moomoo import KLType, TrdEnv

from config import (
    FABIO_DISPLAY_EQUITY_START,
    FABIO_MODELED_EQUITY_ENABLED,
    FABIO_MOOMOO_REFERENCE_EQUITY,
)
from fabio_live.constants import MARKET_TIMEZONE, PAPER_TRADING

_CANDLE_CACHE: dict[tuple[str, str, int], pd.DataFrame] = {}
_MARKET_TZ = ZoneInfo(MARKET_TIMEZONE)


def _normalize_candles(data: pd.DataFrame) -> pd.DataFrame:
    df = data[["time_key", "open", "close", "high", "low", "volume"]].copy()
    df["time_key"] = pd.to_datetime(df["time_key"], errors="coerce")
    for col in ("open", "close", "high", "low", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["time_key", "open", "close", "high", "low"])
    df = df.sort_values("time_key").drop_duplicates(subset=["time_key"], keep="last")
    return df.reset_index(drop=True)


def _bar_seconds(ktype: KLType) -> int:
    if ktype == KLType.K_3M:
        return 180
    if ktype == KLType.K_5M:
        return 300
    if ktype == KLType.K_15M:
        return 900
    if ktype == KLType.K_DAY:
        return 86400
    return 300


def candle_age_seconds(df: pd.DataFrame) -> float:
    if df.empty:
        return float("inf")
    ts = pd.Timestamp(df["time_key"].iloc[-1])
    if ts.tzinfo is None:
        ts = ts.tz_localize(_MARKET_TZ)
    return max(0.0, (pd.Timestamp.now(tz=_MARKET_TZ) - ts).total_seconds())


def get_candles(
    quote_ctx,
    symbol: str,
    ktype: KLType,
    count: int = 100,
    retries: int = 3,
    retry_sleep_sec: float = 0.8,
    allow_cached_fallback: bool = True,
) -> pd.DataFrame:
    """Subscribe then fetch OHLCV candles from Moomoo."""
    from moomoo import SubType

    code = f"US.{symbol}"
    cache_key = (symbol, str(ktype), int(count))
    kl_to_sub = {
        KLType.K_DAY: SubType.K_DAY,
        KLType.K_5M: SubType.K_5M,
        KLType.K_3M: SubType.K_3M,
        KLType.K_15M: SubType.K_15M,
    }
    sub_type = kl_to_sub.get(ktype, SubType.K_5M)
    last_err = None

    for attempt in range(1, retries + 1):
        try:
            quote_ctx.subscribe([code], [sub_type], subscribe_push=False)
            result = quote_ctx.get_cur_kline(code, count, ktype)
            ret, data = result[0], result[1]
            if ret != 0:
                raise RuntimeError(f"ret={ret} data={data}")
            df = _normalize_candles(data)
            if df.empty:
                raise RuntimeError("empty dataframe after normalization")

            _CANDLE_CACHE[cache_key] = df.copy()
            return df
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(retry_sleep_sec * attempt)

    if allow_cached_fallback and cache_key in _CANDLE_CACHE:
        cached = _CANDLE_CACHE[cache_key].copy()
        age_sec = candle_age_seconds(cached)
        print(
            f"  ⚠  [{symbol}] Using cached {ktype} candles "
            f"(age={age_sec/60:.1f}m) after fetch failure: {last_err}"
        )
        return cached

    raise RuntimeError(f"Candle fetch failed for {symbol} {ktype}: {last_err}")


def get_candles_fresh(
    quote_ctx,
    symbol: str,
    ktype: KLType,
    count: int,
    max_age_bars: float = 2.0,
    retries: int = 3,
) -> pd.DataFrame:
    """
    Fetch candles and enforce a freshness bound.

    max_age_bars=2 means last bar can be up to 2 bar-lengths old before retry.
    """
    bar_sec = _bar_seconds(ktype)
    max_age_sec = max_age_bars * bar_sec
    last_df = pd.DataFrame()
    for attempt in range(1, retries + 1):
        df = get_candles(
            quote_ctx,
            symbol,
            ktype,
            count=count,
            retries=2,
            retry_sleep_sec=0.5,
            allow_cached_fallback=True,
        )
        last_df = df
        age_sec = candle_age_seconds(df)
        if age_sec <= max_age_sec:
            return df
        if attempt < retries:
            print(
                f"  ⚠  [{symbol}] {ktype} stale ({age_sec/60:.1f}m old), retrying..."
            )
            time.sleep(0.6 * attempt)
    return last_df


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def compute_atr(df: pd.DataFrame, period: int = 14) -> float:
    high, low, close = df["high"], df["low"], df["close"]
    tr = pd.concat(
        [
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean().iloc[-1]


def get_vix(quote_ctx) -> float | None:
    """
    Fetch live VIX from yfinance only.

    We intentionally bypass Moomoo for VIX because US.VIX snapshots have been
    unreliable in this setup.
    """
    try:
        import yfinance as yf

        hist = yf.Ticker("^VIX").history(period="1d", interval="1m")
        if not hist.empty:
            val = float(hist["Close"].iloc[-1])
            print(f"  VIX (yfinance): {val:.2f}")
            return val
        print("  ⚠  yfinance VIX returned empty data")
    except Exception as e:
        print(f"  ⚠  yfinance VIX error: {e}")

    print("  ⚠  VIX unavailable — marking feed degraded (entry blocked)")
    return None


def modeled_equity_from_raw(raw_total_assets: float) -> float:
    """
    Map broker total_assets into a smaller test book without changing fill-level P&L.
    modeled = display_start + (raw - moomoo_reference)
    """
    if not FABIO_MODELED_EQUITY_ENABLED:
        return float(raw_total_assets)
    return float(
        FABIO_DISPLAY_EQUITY_START + (raw_total_assets - FABIO_MOOMOO_REFERENCE_EQUITY)
    )


def raw_total_assets(trade_ctx) -> float | None:
    """
    Moomoo total_assets from accinfo_query (no transform).
    Returns None if the query fails (same ret check as get_portfolio_value).
    """
    ret, data = trade_ctx.accinfo_query(
        trd_env=TrdEnv.SIMULATE if PAPER_TRADING else TrdEnv.REAL
    )
    if ret != 0 or data is None or data.empty:
        return None
    return float(data["total_assets"].iloc[0])


def get_portfolio_value(trade_ctx) -> float:
    raw = raw_total_assets(trade_ctx)
    if raw is None:
        return (
            FABIO_DISPLAY_EQUITY_START if FABIO_MODELED_EQUITY_ENABLED else 100_000.0
        )
    return modeled_equity_from_raw(raw)
