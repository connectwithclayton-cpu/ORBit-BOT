# Morning Audit

Copy/paste checklist to verify bot health, dashboard freshness behavior, and low-overlap execution before market activity.

## TL;DR

```bash
cd "/Users/claytonjohnson/Documents/TRADING/Fabio_bot"
python3 print_effective_config.py
python3 verify_phase2_reliability.py
python3 orb_bot_fabio.py
```

In a second terminal:

```bash
cd "/Users/claytonjohnson/Documents/TRADING/Fabio_bot"
tail -f bot_health_snapshots.jsonl
```

## 1) Preflight (run first)

```bash
cd "/Users/claytonjohnson/Documents/TRADING/Fabio_bot"
python3 print_effective_config.py
python3 verify_phase2_reliability.py
```

### Pass criteria
- No hard-stop reliability failures.
- Config mode and env values match expected session setup.

## 2) Start bot

```bash
python3 orb_bot_fabio.py
```

### If the bot shows `Skipped — bot paused` immediately

1. Check the first `[Startup] STARTUP_PREFLIGHT …` line: `broker_open_positive_qty` vs `adoptable_precheck`.
2. Check Sheets `Alerts` (or console) for `RECONCILE` / `DATA_FEED` rows with tags like `[reconcile_auto_adopt_none]` or `[vix_unavailable]`.
3. Send Telegram `/status` and read `PauseReason`, `PauseHint`, and `Startup reconcile pending rows`.
4. **Fix root cause before relying on `/resume` alone** (bad option cost basis in broker snapshot, orphan positions you did not intend, or VIX/data feed). Full table and recovery order: [README.md — Startup paused: reconcile triage](../README.md#startup-paused-reconcile-triage).

## 3) Monitor health snapshots

In another terminal:

```bash
cd "/Users/claytonjohnson/Documents/TRADING/Fabio_bot"
tail -f bot_health_snapshots.jsonl
```

## 4) Ops counters to watch

From each snapshot, inspect `ops`:

- `queue_depth`
- `errors`
- `dropped_noncritical`
- `coalesced_updates`
- `dashboard_intraday_refresh_requests`
- `dashboard_intraday_refresh_enqueued`
- `dashboard_intraday_refresh_throttled`
- `dashboard_open_refresh_requests`
- `dashboard_open_refresh_enqueued`
- `dashboard_open_refresh_throttled`

## 5) Healthy vs warning patterns

### Healthy
- `queue_depth` stays low/oscillating (not steadily climbing).
- `errors` remains unchanged.
- `dashboard_*_requests` increases during activity.
- `dashboard_*_throttled` is non-zero (expected; throttle protection active).
- `dashboard_*_enqueued` grows slower than requests.

### Warning
- `queue_depth` trends upward continuously.
- `errors` increases repeatedly.
- `dropped_noncritical` spikes quickly.
- `dashboard_*_enqueued` almost equals requests while queue also grows.

## 6) Quick mitigation (no code changes)

If warnings appear, restart from a shell that sets slower dashboard refresh cadence:

```bash
cd "/Users/claytonjohnson/Documents/TRADING/Fabio_bot"
export FABIO_DASHBOARD_REFRESH_THROTTLE_SEC=5
export FABIO_DASHBOARD_OPEN_REFRESH_THROTTLE_SEC=120
python3 orb_bot_fabio.py
```

If still noisy:

```bash
cd "/Users/claytonjohnson/Documents/TRADING/Fabio_bot"
export FABIO_DASHBOARD_REFRESH_THROTTLE_SEC=15
export FABIO_DASHBOARD_OPEN_REFRESH_THROTTLE_SEC=300
python3 orb_bot_fabio.py
```

## 7) End-of-day operational sequence (safe order)

```bash
cd "/Users/claytonjohnson/Documents/TRADING/Fabio_bot"
python3 verify_phase2_reliability.py
python3 reconcile_moomoo_to_sheets.py --dry-run
python3 reconcile_moomoo_to_sheets.py
python3 scripts/audit_moomoo_sync.py --eod --lookback-min 480
bash scripts/summarize_audit_sync.sh audit_sync.jsonl
```

## 8) Fast triage commands

```bash
cd "/Users/claytonjohnson/Documents/TRADING/Fabio_bot"
tail -f orb_bot_fabio.log
tail -f audit_sync_scheduler.log
```

## 9) Open-position entry overlay note

- Open inventory in dashboard remains broker-truth.
- `Entry`, `Entry $`, `VIX`, and `OR/ATR` are display-only enrichment from in-memory runtime state when available.
- After restart/adopt scenarios, these fields can temporarily fall back to broker-derived placeholders until fresh in-session metadata is tracked.

