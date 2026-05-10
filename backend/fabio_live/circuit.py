"""ORBIT-style risk circuit breaker for live entries."""

from __future__ import annotations

from fabio_live.constants import (
    CB_DAILY_LOSS_PCT,
    CB_MAX_LOSS_STREAK,
    CB_MAX_OPEN_POS,
    CB_MAX_TRADES,
)


class RiskCircuitBreaker:
    """
    ORBIT hard limits — evaluated before every new entry.
    Records trade results to track daily loss, streak, and trade count.
    """

    def __init__(self):
        self.portfolio_at_open = 0.0
        self.realized_pnl = 0.0
        self.trade_count = 0
        self.loss_streak = 0

    def set_portfolio_open(self, value: float):
        self.portfolio_at_open = value

    @property
    def daily_loss_pct(self) -> float:
        if self.portfolio_at_open <= 0:
            return 0.0
        return self.realized_pnl / self.portfolio_at_open

    def can_enter(self, n_open: int) -> tuple[bool, str]:
        """Returns (allowed, reason). Check before every entry."""
        if self.daily_loss_pct <= -CB_DAILY_LOSS_PCT:
            return False, (
                f"Daily loss {self.daily_loss_pct*100:.1f}% "
                f"hit -{CB_DAILY_LOSS_PCT*100:.0f}% limit"
            )
        # Match research backtest semantics:
        # - daily trade cap applies to completed trades only
        # - open-position cap applies independently
        if self.trade_count >= CB_MAX_TRADES:
            return False, f"Daily trade cap reached ({self.trade_count}/{CB_MAX_TRADES})"
        if n_open >= CB_MAX_OPEN_POS:
            return False, f"Max open positions ({n_open}/{CB_MAX_OPEN_POS})"
        return True, ""

    def size_modifier(self) -> float:
        """Cut size 50% after 3 consecutive losses."""
        return 0.5 if self.loss_streak >= CB_MAX_LOSS_STREAK else 1.0

    def record_result(self, pnl_dollars: float):
        """Call after each trade closes."""
        self.realized_pnl += pnl_dollars
        self.trade_count += 1
        if pnl_dollars < 0:
            self.loss_streak += 1
        else:
            self.loss_streak = 0

    def reset(self):
        self.portfolio_at_open = 0.0
        self.realized_pnl = 0.0
        self.trade_count = 0
        self.loss_streak = 0

    def summary(self) -> str:
        return (
            f"CB | DayPnL={self.daily_loss_pct*100:.1f}% | "
            f"Trades={self.trade_count}/{CB_MAX_TRADES} | "
            f"LossStreak={self.loss_streak}"
        )
