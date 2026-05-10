# Phase 2 Decision Note: Live Exit Timeframe

Status: deferred by operator decision during Phase 1 safety-first hardening.

## Current Live Behavior

- Live exits are evaluated on 3-minute bars in `backend/fabio_live/bot.py`.
- `SignalEngine.exit_timeframe()` is still computed and logged at entry, but not used to drive live exit evaluations.

## Decision Required in Phase 2

Choose one and implement end-to-end (code + tests + operator docs):

1. Standardize on fixed 3-minute exits.
   - Remove `exit_tfs` bookkeeping and related logging to eliminate dead concepts.
2. Implement true dynamic exit timeframe.
   - Wire `SignalEngine.exit_timeframe()` output into `run_exit_loop`.
   - Ensure 3m/5m/15m data freshness contracts and fallback behavior are explicit.

## Required Acceptance Criteria

- One clearly documented behavior in README and operator status output.
- Tests cover selected behavior under stale-feed and normal-feed conditions.
- No ambiguous logs that imply dynamic behavior when fixed behavior is active.
