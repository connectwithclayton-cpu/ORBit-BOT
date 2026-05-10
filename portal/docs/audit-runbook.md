# Sync Audit Runbook

## Purpose
Operate and troubleshoot the Moomoo-authoritative sync audit that checks broker, Sheets, and dashboard consistency.

## Publishing rule (prevent drift)

After material paper SIMULATE fills (especially before trusting KPIs):

1. **Publish** canonical surfaces from broker (not `--dry-run`):
   ```bash
   PYTHONPATH=backend:frontend python3 backend/reconcile_moomoo_to_sheets.py
   ```
   Dry-run prints counts only — it does **not** write `trade_data.json`, HTML, or replace **Broker Fills / Reconciled Trades / Open Inventory** tabs.
2. **Confirm** no `RECONCILE_MISMATCH` in logs (broker open inventory must equal FIFO-derived opens). If it appears, fix OpenD/inventory visibility and rerun — do not hand-edit canonical tabs.
3. **Verify** with full-stack audit when investigating “missing today’s positions”:
   ```bash
   PYTHONPATH=backend:frontend python3 backend/audit_full_positions.py
   ```
4. **Intraday** rolling check (market window): keep `backend/scripts/audit_moomoo_sync.py` on schedule per below.

Optional pre-open linkage to the scheduler audit log:

```bash
PYTHONPATH=backend:frontend python3 backend/verify_canonical_publish.py --jsonl audit_sync.jsonl --max-age-min 120
# Or combined with Phase 2 gate:
PYTHONPATH=backend:frontend python3 backend/verify_phase2_reliability.py --sync-audit-jsonl audit_sync.jsonl --sync-audit-max-age-min 120
```

## RECONCILE_MISMATCH triage

- Symptom: log line `reconcile mismatch: broker_open=... computed_open=...` and canonical tabs/dashboard **not** updated for that run.
- Actions: reconcile **broker** snapshot (`position_list_query`) vs **FIFO-derived** opens (same symbols/qty); fix missing fills in history, stale OpenD cache, or same-session partial lot bugs; rerun reconcile.
- Do **not** patch KPI tabs manually to match the broker — fix the invariant so publish succeeds once.

## Interpreting “today looks short”

The dashboard counts **FIFO closed segments** (each partial exit can be multiple rows per symbol/date). Compare per-date counts printed by `audit_full_positions.py` (FIFO vs `trade_data.json` vs Sheets).

## Files
- Runner: `backend/scripts/audit_moomoo_sync.py`
- Full stack: `backend/audit_full_positions.py` (entire SIMULATE history vs Sheets + dashboard)
- Canonical publish gate: `backend/verify_canonical_publish.py`
- Wrapper: `backend/scripts/run_moomoo_sync_audit.sh`
- Scheduler installer: `portal/install_sync_audit_scheduler.sh`
- Summary: `backend/scripts/summarize_audit_sync.sh`
- Log artifact: `audit_sync.jsonl`
- State file: `audit_sync_state.json`

## Standard Commands
From the **Fabio_bot** project root (set `export PYTHONPATH=backend:frontend`):

```bash
PYTHONPATH=backend:frontend python3 backend/scripts/audit_moomoo_sync.py --dry-run --lookback-min 180
PYTHONPATH=backend:frontend python3 backend/scripts/audit_moomoo_sync.py --lookback-min 180
PYTHONPATH=backend:frontend python3 backend/scripts/audit_moomoo_sync.py --eod --lookback-min 480
bash backend/scripts/summarize_audit_sync.sh audit_sync.jsonl
```

Install scheduler:

```bash
bash portal/install_sync_audit_scheduler.sh
```

## Alerts and Escalation
- Default: alert only after 2 consecutive failures.
- Triggered on:
  - Missing broker fill IDs in Sheets
  - Inventory mismatch (Moomoo vs Open Inventory)
  - Per-day P&L mismatch above tolerance
  - Repeated EOD drift

## Triage Checklist
1. **Live bot paused at startup (entries blocked):** this is separate from sync audit but often shows up as broker inventory vs strategy drift. See [README.md — Startup paused: reconcile triage](../../README.md#startup-paused-reconcile-triage) (pause reason codes, cost-basis checks, `STARTUP_PREFLIGHT` logs).
2. Check last records:
   - `bash backend/scripts/summarize_audit_sync.sh audit_sync.jsonl`
3. If missing broker fills:
   - Run reconcile dry-run:
     - `PYTHONPATH=backend:frontend python3 backend/reconcile_moomoo_to_sheets.py --dry-run`
   - Confirm Moomoo connectivity/OpenD health.
4. If inventory mismatch:
   - Verify open positions in Moomoo paper account.
   - Compare with `Open Inventory` tab.
   - Re-run reconcile publish after mismatch is understood.
5. If dashboard P&L mismatch:
   - Check `Reconciled Trades` totals by date.
   - Regenerate dashboard from canonical reconcile outputs.
6. Confirm next audit run passes before clearing incident.

## Performance Guardrails
- Keep audit runtime under 10 seconds target.
- Wrapper lock prevents overlap.
- Wrapper timeout prevents process pile-up.
- Keep lookback practical (e.g., 180-480 min) for intraday frequency.

## Recovery
- If scheduler jobs fail repeatedly:
  - `launchctl print "gui/$(id -u)/com.claytonorb.fabio.syncaudit.15m"`
  - `launchctl print "gui/$(id -u)/com.claytonorb.fabio.syncaudit.eod"`
  - Tail scheduler log: `tail -f audit_sync_scheduler.log`
- Manual fallback:
  - Run `backend/scripts/run_moomoo_sync_audit.sh` directly.

## Expected Steady State
- Frequent `PASS` events during market hours.
- `FAIL` events are rare and actionable.
- EOD run confirms no unresolved drift.
