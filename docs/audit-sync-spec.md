# Moomoo-Authoritative Sync Audit Spec

## Goal
Continuously verify that closed options activity in Moomoo is represented correctly in:
- Google Sheets canonical tabs
- Dashboard data (`trade_data.json` and rollups)

Moomoo is authoritative for closed-fill and open-inventory truth.

## Scope
- Account: Moomoo SIMULATE (`TrdEnv.SIMULATE`)
- Instruments: US options only (`[A-Z]+YYMMDD(C|P)strike` code pattern)
- Activities:
  - Closed option fills: SELL-side filled/partially filled history rows
  - Open option inventory: position quantities by code

## Data Surfaces and Contracts
- Broker:
  - `history_order_list_query(...)` filtered to SELL + option code
  - `position_list_query(...)` filtered to option code + qty > 0
- Sheets:
  - `Broker Fills` tab
  - `Reconciled Trades` tab
  - `Open Inventory` tab
- Dashboard:
  - `trade_data.json` (`trades`, `daily`)

## Canonical Keys
- Broker fill identity:
  - `fill_id = "{updated_time}|{code}|{side}|{qty}|{price:.4f}"`
- Inventory identity:
  - `code -> sum(qty)` for qty > 0
- Day P&L identity:
  - `date -> net_pnl` for reconciled and dashboard daily rows

## Layered Checks
1. **Completeness**
   - Moomoo closed SELL fill IDs must exist in Sheets `Broker Fills` for the same lookback.
2. **Uniqueness**
   - No duplicate fill IDs in Sheets `Broker Fills`.
3. **Inventory consistency**
   - Moomoo open inventory (`code->qty`) equals Sheets `Open Inventory` totals.
4. **P&L consistency**
   - Per-day net P&L in `Reconciled Trades` equals dashboard `daily.net_pnl` within tolerance.
5. **Classification integrity**
   - Backfill rows must not be session-included KPI rows.

## Default Tolerances
- P&L delta tolerance: `0.01`
- Runtime budget per run: `<= 10s` target (`<= 20s` hard wrapper timeout)
- Alert threshold: `>= 2` consecutive failures

## Scheduling Policy
- 15-minute audit cadence during weekdays (execution window gates inside script).
- Post-close EOD confirmation run at ~4:03 PM ET.
- Audit and trading loops must remain isolated:
  - Separate process
  - Lockfile overlap protection
  - Jitter + timeout guardrails

## Severity Policy
- `INFO`: pass / skipped outside window
- `WARNING`: first hard drift, soft drift, or runtime budget overrun
- `CRITICAL`: repeated hard drift or unresolved EOD drift

## Outputs
- `audit_sync.jsonl`: append-only records with checks, drift details, severity, latency
- `audit_sync_state.json`: consecutive-failure state for alert gating

## Exit Codes
- `0`: pass or intentional non-market skip
- `1`: drift failure
- `2`: runtime/config error
