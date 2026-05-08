"""Vectorized-style event backtest: one engine, two modes (research vs live mirror)."""

from __future__ import annotations

from enum import Enum

import pandas as pd

from fabio.options import option_price
from fabio.regime import DayRegime, OpeningRangeStyle
from fabio import signals
from fabio.settings import FabioBacktestSettings


class BacktestMode(str, Enum):
    RESEARCH = "research"
    LIVE_MIRROR = "live_mirror"


class FabioBacktestEngine:
    def __init__(self, settings: FabioBacktestSettings):
        self.cfg = settings

    def run(
        self, data: dict, vix_daily: pd.DataFrame, mode: BacktestMode
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        cfg = self.cfg
        or_style = (
            OpeningRangeStyle.RESEARCH
            if mode == BacktestMode.RESEARCH
            else OpeningRangeStyle.LIVE_MIRROR
        )
        entry_fn = (
            signals.check_entry_research
            if mode == BacktestMode.RESEARCH
            else signals.check_entry_live_mirror
        )

        capital = cfg.initial_capital
        trades: list[dict] = []
        equity: list[dict] = []

        all_days = sorted(set(d.date() for sym in cfg.symbols for d in data[sym]["daily"].index))
        loss_streak = 0

        for date in all_days:
            date_ts = pd.Timestamp(date)
            # Intraday decisions cannot know the same-day VIX daily close.
            vix_row = vix_daily[vix_daily.index.normalize() < date_ts]
            vix = float(vix_row["Close"].iloc[-1]) if not vix_row.empty else 18.0

            day_trades = 0
            day_start_cap = capital
            day_pnl = 0.0
            open_positions: dict = {}
            contexts: dict = {}
            event_times: set[pd.Timestamp] = set()

            for sym in cfg.symbols:
                daily_df = data[sym]["daily"]
                intraday_df = data[sym]["intraday"]

                prior_daily = daily_df[daily_df.index.normalize() < date_ts]
                today_daily = daily_df[daily_df.index.normalize() == date_ts]
                if len(prior_daily) < 20:
                    continue

                i_slice = intraday_df[intraday_df.index.date == date]
                if i_slice.empty:
                    continue

                try:
                    session_open = (
                        float(today_daily["Open"].iloc[0])
                        if not today_daily.empty
                        else float(i_slice["Open"].iloc[0])
                    )
                    regime = DayRegime(
                        cfg,
                        sym,
                        prior_daily,
                        i_slice,
                        vix,
                        or_style,
                        session_open=session_open,
                    )
                except Exception:
                    continue

                if not regime.tradeable:
                    continue

                signal_window = i_slice.between_time("09:45", "14:00")
                if signal_window.empty:
                    continue

                i3m_day = data[sym].get("intraday_3m", pd.DataFrame())
                if not i3m_day.empty:
                    i3m_day = i3m_day[i3m_day.index.date == date]
                    exit_schedule = i3m_day["Close"]
                    exit_tf = "3m"
                else:
                    exit_schedule = (
                        i_slice[i_slice.index > signal_window.index[0]]["Close"]
                        .resample("5min")
                        .last()
                        .dropna()
                    )
                    exit_tf = "5m"

                contexts[sym] = {
                    "regime": regime,
                    "i_slice": i_slice,
                    "i3m_day": i3m_day,
                    "signal_window": signal_window,
                    "exit_schedule": exit_schedule,
                    "exit_tf": exit_tf,
                }
                event_times.update(signal_window.index[2:])
                event_times.update(exit_schedule.index)

            for ts in sorted(event_times):
                # Process exits first so realized P&L and freed slots affect entries.
                for sym in list(open_positions.keys()):
                    pos = open_positions[sym]
                    exit_bars = pos["exit_bars"]
                    if ts not in exit_bars.index:
                        continue

                    close_raw = exit_bars.loc[ts]
                    close_px = (
                        float(close_raw.iloc[-1])
                        if hasattr(close_raw, "iloc")
                        else float(close_raw)
                    )
                    pos["candles_since_entry"] += 1
                    direction = pos["direction"]
                    entry_price_stock = pos["entry_price_stock"]
                    entry_opt_px = pos["entry_opt_px"]
                    regime = pos["regime"]

                    delta = close_px - entry_price_stock
                    if direction == "PUT":
                        delta = -delta
                    lev = entry_opt_px / entry_price_stock * 100
                    curr_opt = max(0.01, entry_opt_px + (delta * lev))

                    if (
                        not pos["profit_locked"]
                        and curr_opt >= entry_opt_px * cfg.profit_lock_multiple
                    ):
                        pos["profit_locked"] = True

                    target = entry_opt_px * (cfg.trim_multiple ** (pos["trim_level"] + 1))
                    if curr_opt >= target and pos["remaining"] >= 2:
                        trim_qty = max(1, int(pos["remaining"] * cfg.trim_pct))
                        sell_px = curr_opt * (1 - cfg.slippage_pct / 2)
                        pos["trim_pnl"] += (sell_px - entry_opt_px) * trim_qty * 100
                        pos["trim_pnl"] -= cfg.commission * trim_qty
                        pos["remaining"] -= trim_qty
                        pos["trim_level"] += 1

                    exit_reason = None
                    atr_stop = regime.atr * 2.0
                    is_eod_bar = ts.hour > 15 or (ts.hour == 15 and ts.minute >= 45)

                    if direction == "CALL" and close_px < entry_price_stock - atr_stop:
                        exit_reason = (
                            "Hard Stop 2×ATR"
                            if mode == BacktestMode.RESEARCH
                            else "Hard Stop 2xATR"
                        )
                    elif direction == "PUT" and close_px > entry_price_stock + atr_stop:
                        exit_reason = (
                            "Hard Stop 2×ATR"
                            if mode == BacktestMode.RESEARCH
                            else "Hard Stop 2xATR"
                        )

                    if exit_reason is None and not pos["profit_locked"]:
                        if not pos["i3m_day"].empty:
                            window_to_ts = pos["i3m_day"][pos["i3m_day"].index <= ts]
                        else:
                            window_to_ts = pos["after_entry"][
                                pos["after_entry"].index <= ts
                            ]
                        if not window_to_ts.empty and signals.check_exit(
                            window_to_ts,
                            direction,
                            regime,
                            candles_since_entry=pos["candles_since_entry"],
                        ):
                            exit_reason = "Strategy exit"

                    if exit_reason is None and is_eod_bar:
                        exit_reason = "EOD"

                    if exit_reason is None:
                        continue

                    price_delta = close_px - entry_price_stock
                    if direction == "PUT":
                        price_delta = -price_delta
                    option_leverage = entry_opt_px / entry_price_stock * 100
                    pnl_per_contract = price_delta * option_leverage * 100
                    final_pnl = pnl_per_contract * pos["remaining"]
                    final_pnl -= cfg.commission * pos["remaining"]
                    max_loss = -entry_opt_px * pos["remaining"] * 100
                    final_pnl = max(final_pnl, max_loss)
                    exit_opt_px = entry_opt_px + (
                        final_pnl / max(pos["remaining"], 1) / 100
                    )
                    total_pnl = pos["trim_pnl"] + final_pnl

                    capital += total_pnl
                    day_pnl += total_pnl
                    day_trades += 1

                    if total_pnl < 0:
                        loss_streak += 1
                    else:
                        loss_streak = 0

                    row = {
                        "date": date,
                        "symbol": sym,
                        "direction": direction,
                        "counter_trend": pos["counter"],
                        "entry_time": pos["entry_time"],
                        "exit_time": ts,
                        "exit_reason": exit_reason,
                        "entry_stock_px": round(entry_price_stock, 2),
                        "exit_stock_px": round(close_px, 2),
                        "entry_opt_px": round(entry_opt_px, 2),
                        "exit_opt_px": round(exit_opt_px, 2),
                        "n_contracts": pos["n_contracts"],
                        "risk_pct": round(pos["risk_pct"] * 100, 2),
                        "trim_pnl": round(pos["trim_pnl"], 2),
                        "final_pnl": round(final_pnl, 2),
                        "total_pnl": round(total_pnl, 2),
                        "capital_after": round(capital, 2),
                        "vix": round(vix, 1),
                        "or_atr_pct": round(regime.or_atr_pct, 1),
                        "gap_pct": round(regime.gap_pct, 2),
                        "exit_tf": pos["exit_tf"],
                    }
                    if mode == BacktestMode.LIVE_MIRROR:
                        row["backtest_mode"] = "live_mirror"
                    trades.append(row)
                    del open_positions[sym]

                for sym in cfg.symbols:
                    if sym not in contexts or sym in open_positions:
                        continue
                    ctx = contexts[sym]
                    signal_window = ctx["signal_window"]
                    if ts not in signal_window.index:
                        continue
                    window = signal_window[signal_window.index <= ts]
                    if len(window) < 3:
                        continue

                    if (day_pnl / day_start_cap) <= -cfg.cb_daily_loss_pct:
                        continue
                    if day_trades >= cfg.cb_max_trades:
                        continue
                    if len(open_positions) >= cfg.cb_max_open_pos:
                        continue

                    regime = ctx["regime"]
                    direction = entry_fn(window, regime)
                    if not direction:
                        continue

                    counter = (direction == "CALL" and not regime.bullish) or (
                        direction == "PUT" and regime.bullish
                    )
                    if counter:
                        continue

                    if regime.vix < (cfg.vix_half_max + 0.1):
                        continue
                    if (
                        direction == "CALL"
                        and cfg.vix_normal_max < regime.vix <= cfg.vix_aggressive_max
                    ):
                        continue

                    cb_mod = 0.5 if loss_streak >= cfg.cb_max_loss_streak else 1.0
                    risk_pct = regime.risk_multiplier(counter=counter, cb_mod=cb_mod)
                    risk_dollars = (
                        min(
                            capital,
                            cfg.initial_capital * cfg.research_risk_capital_multiplier,
                        )
                        * risk_pct
                    )

                    entry_price_stock = float(window["Close"].iloc[-1])
                    entry_opt_px = option_price(
                        direction, entry_price_stock, cfg.option_dte, cfg
                    )
                    entry_opt_px *= 1 + cfg.slippage_pct / 2
                    if entry_opt_px <= 0:
                        continue

                    n_contracts = max(1, int(risk_dollars / (entry_opt_px * 100)))
                    after_entry = ctx["i_slice"][ctx["i_slice"].index > ts]
                    if not ctx["i3m_day"].empty:
                        exit_bars = ctx["i3m_day"][ctx["i3m_day"].index > ts]["Close"]
                    else:
                        exit_bars = after_entry["Close"].resample("5min").last().dropna()
                    if exit_bars.empty:
                        continue

                    open_positions[sym] = {
                        "direction": direction,
                        "counter": counter,
                        "entry_time": ts,
                        "entry_price_stock": entry_price_stock,
                        "entry_opt_px": entry_opt_px,
                        "n_contracts": n_contracts,
                        "risk_pct": risk_pct,
                        "remaining": n_contracts,
                        "trim_pnl": 0.0,
                        "trim_level": 0,
                        "profit_locked": False,
                        "candles_since_entry": 0,
                        "regime": regime,
                        "after_entry": after_entry,
                        "i3m_day": ctx["i3m_day"],
                        "exit_bars": exit_bars,
                        "exit_tf": ctx["exit_tf"],
                    }

            equity.append({"date": date, "capital": round(capital, 2), "day_pnl": round(day_pnl, 2)})

        return pd.DataFrame(trades), pd.DataFrame(equity)
