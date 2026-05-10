"""Canonical exit reason taxonomy for forward-only attribution."""

from __future__ import annotations

from dataclasses import dataclass


REASON_SOURCE_STRATEGY = "strategy"
REASON_SOURCE_RECONCILE = "reconcile"
REASON_SOURCE_MANUAL = "manual"

CODE_OPEN = "OPEN"
CODE_PROFIT_TRIM = "PROFIT_TRIM"
CODE_PROFIT_LOCK_CLOSE = "PROFIT_LOCK_CLOSE"
CODE_EMA_CROSS = "EMA_CROSS"
CODE_OR_MIDPOINT = "OR_MIDPOINT"
CODE_ATR_HARD_STOP = "ATR_HARD_STOP"
CODE_EOD_CLOSE = "EOD_CLOSE"
CODE_FORCE_CLOSE = "FORCE_CLOSE"
CODE_RECONCILED_CLOSE = "RECONCILED_CLOSE"
CODE_OTHER = "OTHER"


_DISPLAY_BY_CODE = {
    CODE_OPEN: "Open",
    CODE_PROFIT_TRIM: "Profit trim",
    CODE_PROFIT_LOCK_CLOSE: "Profit lock close",
    CODE_EMA_CROSS: "EMA crossover",
    CODE_OR_MIDPOINT: "OR midpoint",
    CODE_ATR_HARD_STOP: "ATR hard stop",
    CODE_EOD_CLOSE: "EOD close",
    CODE_FORCE_CLOSE: "Force close",
    CODE_RECONCILED_CLOSE: "Reconciled fill close",
    CODE_OTHER: "Other",
}


_CODE_BY_REASON_LOWER = {
    "open": CODE_OPEN,
    "profit trim": CODE_PROFIT_TRIM,
    "profit lock (trim flat)": CODE_PROFIT_LOCK_CLOSE,
    "ema cross": CODE_EMA_CROSS,
    "ema crossover": CODE_EMA_CROSS,
    "ema 10/20 cross": CODE_EMA_CROSS,
    "ema 10/20 cross on 3-min": CODE_EMA_CROSS,
    "or midpoint": CODE_OR_MIDPOINT,
    "or re-entry": CODE_OR_MIDPOINT,
    "atr stop": CODE_ATR_HARD_STOP,
    "hard stop 2xatr": CODE_ATR_HARD_STOP,
    "hard stop 2×atr": CODE_ATR_HARD_STOP,
    "eod": CODE_EOD_CLOSE,
    "eod close": CODE_EOD_CLOSE,
    "force close": CODE_FORCE_CLOSE,
    "reconciled fill close": CODE_RECONCILED_CLOSE,
    "moomoo fill backfill": CODE_RECONCILED_CLOSE,
}


@dataclass(frozen=True)
class ExitReason:
    code: str
    label: str
    source: str
    detail: str


def canonical_exit_reason(
    reason: str | None,
    *,
    source: str,
    detail: str | None = None,
) -> ExitReason:
    """Normalize a free-form reason into canonical code/label/source/detail."""
    raw = str(reason or "").strip()
    key = raw.lower()
    code = _CODE_BY_REASON_LOWER.get(key, CODE_OTHER)
    label = _DISPLAY_BY_CODE.get(code, raw or _DISPLAY_BY_CODE[CODE_OTHER])
    return ExitReason(
        code=code,
        label=label if label else (raw or _DISPLAY_BY_CODE[CODE_OTHER]),
        source=str(source or "").strip().lower() or REASON_SOURCE_MANUAL,
        detail=str(detail or raw or "").strip(),
    )

