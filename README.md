# Fabio ORB backtest

Python backtest for a **Fabio / ORBit-style opening range breakout** strategy with **0DTE-style options simulation** (Black–Scholes, fixed DTE, slippage, commissions). This repo also contains related **live** helpers (`orb_bot_fabio.py`, dashboard, logging); the main research entry point is `Fabio_orb_backtest.py`.

**Disclaimer:** Backtests are not predictions. Past results do not guarantee future performance. This is research tooling, not financial advice.

---

## Requirements

- **Python 3.10+** (the script uses modern type hints such as `str | None`). **GitHub Actions CI uses Python 3.11** — use **3.11** locally for the closest match to CI. On **3.13+**, some third-party libraries (e.g. protobuf via `moomoo-api`) may emit `DeprecationWarning` at import time; the test suite configures pytest to filter the known protobuf case only.
- Install core dependencies (versions are **pinned** in `requirements.txt` for reproducibility):

```bash
pip install -r requirements.txt
```

- For an **exact** transitive snapshot (as produced by `pip freeze` after installing core deps), use:

```bash
pip install -r requirements.lock
```

- Optional integrations (Google Sheets logging):

```bash
pip install -r requirements-optional.txt
```

- Tests and dev tools (`requirements-dev.txt` **includes** core deps via `-r requirements.txt`; one install is enough for `pytest`):

```bash
pip install -r requirements-dev.txt
python3 -m pytest tests/ -v
```

To **refresh** pins after upgrading packages: reinstall into a clean venv, run `pip freeze > requirements.lock`, and update `==` lines in `requirements.txt` / `requirements-optional.txt` / `requirements-dev.txt` for the packages you care about.

---

## Quick start

From this directory:

```bash
python Fabio_orb_backtest.py
```

The script prints a summary to the console and writes CSVs and a chart (see [Outputs](#outputs)).

Pre-flight config check (recommended before live runs and in your pre-open ritual):

```bash
python3 print_effective_config.py
```

If `MOOMOO_TRADE_ENV=REAL`, this script prints a **prominent warning** first; otherwise the sanity summary states SIMULATE.

### Modeled paper equity (Moomoo SIMULATE)

Moomoo paper `total_assets` is often a large notional (e.g. \$1M). The live bot reads `accinfo_query` through `get_portfolio_value()` in [`fabio_live/market_data.py`](fabio_live/market_data.py) and, **in SIMULATE only** (unless you override), applies:

`modeled_equity = FABIO_DISPLAY_EQUITY_START + (raw_total_assets − FABIO_MOOMOO_REFERENCE_EQUITY)`

Defaults: **\$10,000** modeled book vs **\$1,000,000** broker reference (equivalent to subtracting **\$990,000** from raw `total_assets` at that reference).

- **Unchanged:** Per-fill and per-trade dollar P&amp;L rows (Sheets, reconcile FIFO, dashboard legs) stay **broker-scale**.
- **Adjusted:** Reported **capital** end-of-day, **daily return %** denominators, circuit-breaker **daily loss %** base, and **`risk_base = min(portfolio, cap)`** sizing input use the modeled equity.

| Variable | Default | Meaning |
|----------|---------|---------|
| `FABIO_MOOMOO_REFERENCE_EQUITY` | `1000000` | Raw Moomoo equity taken as the reference point |
| `FABIO_DISPLAY_EQUITY_START` | `10000` | Modeled starting book when raw equals the reference |
| `FABIO_MODELED_EQUITY_ENABLED` | unset → **on** for SIMULATE, **off** for REAL | Set `1` / `0` to force |

---

## Backtest runners

- `Fabio_orb_backtest.py` — primary **research** backtest (source of truth). Uses `OpeningRangeStyle.RESEARCH` in the engine: OR = **09:30–09:44 ET** on **5-minute** bars (same definition as the **current** live bot in `fabio_live/regime.py`).
- `Fabio_live_mirror_backtest.py` — **legacy live-mirror** backtest: uses `OpeningRangeStyle.LIVE_MIRROR` in `fabio/regime.py` (OR window **09:30–09:40 ET** on 5m data). This approximates an **older** live-bot OR definition; it does **not** match today’s live bot, which was aligned back to research.
- `FabioOrb_copy_backtest.py` — compatibility wrapper alias to `Fabio_orb_backtest.py` (kept to avoid drift from duplicate code).

---

## Data sources

**Precedence (research runner `Fabio_orb_backtest.py` only):**

1. `FabioBacktestSettings.from_env()` reads optional env `FABIO_DATA_SOURCE` (`polygon` or `yfinance`) into the config object.
2. The module then runs **`_cfg.data_source = DATA_SOURCE`**, where `DATA_SOURCE` is the constant near the top of `Fabio_orb_backtest.py`.

So the **in-file `DATA_SOURCE` always wins** for that script. Env `FABIO_DATA_SOURCE` affects other callers of `FabioBacktestSettings.from_env()` (for example `print_effective_config.py` and live `fabio_live/constants.py`) but **not** the research backtest’s data source unless you change or remove the override in `Fabio_orb_backtest.py`.

| Value | Behavior |
|-------|----------|
| `polygon` | Uses [Polygon.io](https://polygon.io/) for daily + intraday bars (recommended for full history). VIX still comes from **yfinance**. |
| `yfinance` | Uses **yfinance** only (simpler setup; intraday history may be more limited). |

If the effective source is `polygon` but no API key is set, the loader **falls back to yfinance** and prints a warning.

---

## Environment (Polygon)

Use `.env.example` as a template and prefer storing real secrets outside the repo tree.

- Preferred: set `FABIO_ENV_FILE=/secure/path/fabio.env` and keep that file outside this project.
- Legacy fallback: `Fabio_bot/.env` is still supported for local compatibility, but not recommended.

Add:

```env
POLYGON_API_KEY=your_polygon_key_here
# Optional: polygon | yfinance — used by FabioBacktestSettings.from_env() (see Data sources for research script override)
FABIO_DATA_SOURCE=polygon

# Optional: append NDJSON timing lines from Fabio_orb_backtest / legacy mirror (default: off)
# FABIO_BACKTEST_DEBUG_LOG=./fabio_backtest_debug.ndjson
```

Never commit real API keys. Keep `.env` out of git.

Also treat `google_credentials.json` and any service-account credential files as secrets; they should never be committed.

---

## Configuration (edit the script)

Strategy tunables live in `fabio/settings.py` (`FabioBacktestSettings`) and are shared by backtests + live bot.

`config.py` is integrations-only (Moomoo/Telegram/optional Google env values).

**Data source:** Prefer editing `DATA_SOURCE` in `Fabio_orb_backtest.py` for the research backtest, or set `FABIO_DATA_SOURCE` in `.env` for tools that only call `from_env()` (see [Data sources](#data-sources)).

Primary strategy knobs:

- **Universe & dates:** `SYMBOLS`, `START_DATE`, `END_DATE`
- **Capital:** `INITIAL_CAPITAL`
- **Risk (Fabio v5 — half of ORB-style defaults):** `RISK_PCT_*`, `RISK_PCT_MAX`
- **VIX tiers:** `VIX_SKIP`, `VIX_HALF_MAX`, `VIX_NORMAL_MAX`, `VIX_AGGRESSIVE_MAX`
- **Gap / OR quality:** `GAP_SKIP_PCT`, `GAP_RETEST_PCT`, `OR_SKIP_PCT_ATR`, `OR_NORMAL_MIN_ATR`, `OR_WIDE_PCT_ATR`
- **Circuit breakers:** `CB_DAILY_LOSS_PCT`, `CB_MAX_TRADES`, `CB_MAX_LOSS_STREAK`, `CB_MAX_OPEN_POS`
- **Exits / trims:** `TRIM_MULTIPLE`, `TRIM_PCT`, `PROFIT_LOCK_MULTIPLE`
- **Options model:** `IV_BASE`, `OPTION_DTE`, `SLIPPAGE_PCT`, `COMMISSION`

Some comments in the file are marked **TODO** if you want to align thresholds exactly with your written rule set.

---

## Strategy rule subset (as implemented)

This mirrors the logic in `check_entry`, `check_exit`, `DayRegime`, and `run_backtest`:

### Regime / filters

- **Opening range (OR), research + current live bot:** High/low of **5-minute** bars from **09:30–09:44 ET** (`DayRegime` / `MarketRegime` research path). The **legacy live-mirror** backtest uses **09:30–09:40 ET** only (`OpeningRangeStyle.LIVE_MIRROR`); use that runner only for historical comparison, not for parity with today’s bot.
- **VIX:** Risk scaling by VIX band; trades skipped if VIX is below `VIX_SKIP`.
- **Gap:** Skip day if gap ≥ `GAP_SKIP_PCT`. Moderate gaps (`GAP_RETEST_PCT`–`GAP_SKIP_PCT`) require a **retest** near the OR boundary before a breakout counts.
- **OR width vs ATR:** `or_size_factor` scales or skips entries based on OR size relative to ATR.
- **Trend:** Daily EMA10 > EMA20 and close > EMA50 defines **bullish** regime.
- **Counter-trend:** **Disabled** — no trades against the daily trend.
- **Fabio v5 VIX filters (backtest loop):**
  - VIX &lt; ~16.1: **no trades**
  - VIX in elevated band (20–28): **CALL** entries skipped (PUTs allowed)

### Entry (ORBit checklist–style)

- **CALL:** Two consecutive **5-minute closes** above OR high.
- **PUT:** Two consecutive **5-minute closes** below OR low.
- **Window:** Signals scanned **09:45–14:00** ET.

### Exit simulation

- **Bars:** Prefers **3-minute** bars after entry for exit logic; falls back to resampled 5-minute if 3-minute data is missing.
- **Strategy exit:** (1) Two consecutive closes on the wrong side of **OR midpoint**, or (2) **EMA10 vs EMA20** crossover on the exit bar series.
- **Profit lock:** If modeled option P&amp;L reaches `PROFIT_LOCK_MULTIPLE` × entry premium, strategy exits are **disabled** until EOD; **2×ATR** stock stop still applies.
- **Hard stop:** **2×ATR** (daily ATR) move against the position on the underlying.
- **Trim:** Partial exits at multiples of entry premium (`TRIM_*`).
- **EOD:** Positions closed by end of session logic in the loop.

---

## Outputs

Written to the **current working directory** when you run the script (usually this folder):

| File | Contents |
|------|----------|
| `Fabio_backtest_trades.csv` | One row per trade |
| `Fabio_backtest_equity.csv` | Daily equity curve |
| `Fabio_backtest_report.png` | Equity, monthly P&amp;L, win rate, exits, histogram, rolling Sharpe |

---

## Other files in this project (pointers)

| File | Role |
|------|------|
| `orb_bot_fabio.py` | Live bot entrypoint (loads `.env`, runs `ORBBot`) |
| `fabio_live/` | Live stack: `constants`, `market_data`, `regime`, `signals`, `orders`, `circuit`, `async_ops`, `bot` |
| `config.py` | Shared configuration for live tooling |
| `FabioOrb_copy_backtest.py` | Compatibility alias to canonical research backtest |
| `Fabio_live_mirror_backtest.py` | Legacy live-mirror backtest (`BacktestMode.LIVE_MIRROR`) |
| `dashboard_writer.py`, `live_dashboard.html` | Dashboard pipeline |
| `telegram_bot.py`, `sheets_logger.py` | Notifications / logging |

---

## Terminal commands (operations)

**Copy-paste:** Prefer fenced `bash` blocks. Avoid command tables because copied `|` separators can break terminal input.

### Safety rails (run first)

Set working directory:

```bash
cd ~/Documents/TRADING/Fabio_bot
```

Quick environment sanity:

```bash
python3 print_effective_config.py
```

Security-first env-file check (recommended):

```bash
FABIO_ENV_FILE=/secure/path/fabio.env python3 print_effective_config.py
```

Verify key defaults are enabled before live execution:

```bash
python3 - <<'PY'
import os
print('FABIO_OPTIONS_ONLY_EXECUTION=', os.getenv('FABIO_OPTIONS_ONLY_EXECUTION','1'))
print('FABIO_AUTO_ADOPT_OPEN_POSITIONS=', os.getenv('FABIO_AUTO_ADOPT_OPEN_POSITIONS','1'))
PY
```

### Runtime operations

Live bot (foreground/debug):

```bash
python3 orb_bot_fabio.py
```

Follow live bot log:

```bash
tail -f orb_bot_fabio.log
```

Intraday dashboard freshness (isolated from trading loop):

- Ledger mutations (open/trim/close) now enqueue a **coalesced async** dashboard refresh.
- Optional broker open-position snapshot refresh runs via async worker (display-only).
- No blocking dashboard I/O is executed on the trading decision/order path.

Tune cadence with env vars (defaults shown):

```env
FABIO_DASHBOARD_REFRESH_THROTTLE_SEC=2.0
FABIO_DASHBOARD_OPEN_REFRESH_THROTTLE_SEC=60.0
```

Health snapshot counters now include:
- `dashboard_intraday_refresh_requests` / `dashboard_intraday_refresh_enqueued` / `dashboard_intraday_refresh_throttled`
- `dashboard_open_refresh_requests` / `dashboard_open_refresh_enqueued` / `dashboard_open_refresh_throttled`

Rollback / reduce refresh pressure safely (no code changes):

- Increase either throttle value (e.g. `30` and `300`) to slow updates.
- Set very large values to effectively disable frequent intraday refresh behavior.
- Canonical EOD/reconcile flows remain unchanged.

Reliability gate snapshot check:

```bash
python3 verify_phase2_reliability.py
```

Debug board HTML (config + artifacts + log tail):

```bash
python3 debug_board_writer.py
```

### Data sync and canonical reconcile

Dry-run first, then publish canonical tabs and regenerate dashboard:

```bash
python3 reconcile_moomoo_to_sheets.py --dry-run
python3 reconcile_moomoo_to_sheets.py
```

Canonical outputs in Sheets:
- `Broker Fills`
- `Reconciled Trades`
- `Open Inventory`

Precedence notes:
- **`--dry-run`** only prints intentions — it does **not** persist `trade_data.json`, dashboard HTML, or replace canonical tabs (see [docs/audit-runbook.md](docs/audit-runbook.md) publishing rule).
- Successful reconcile sets `trade_data.json -> open_positions` from FIFO/Open Inventory **after** broker vs FIFO inventory matches.
- Bot-only EOD (without reconcile) sets open positions from Moomoo `position_list_query`.
- `RECONCILE_MISMATCH` skips **both** dashboard persistence and canonical tab replaces until resolved.

Full-history consistency check:

```bash
python3 audit_full_positions.py
```

Optional gate on the scheduled sync audit log:

```bash
python3 verify_canonical_publish.py --jsonl audit_sync.jsonl --max-age-min 120
```

### Startup paused: reconcile triage

On process start, `ORBBot` queries Moomoo open positions and may **pause new entries** until orphans are safe to track.

**Console / Sheets signals**

- One-line preflight: `[Startup] STARTUP_PREFLIGHT …` (counts of broker opens vs adoptable pre-check).
- Sheets row type `STARTUP_PREFLIGHT` with the same payload.
- Pause rows use bracketed reason tags, e.g. `[reconcile_auto_adopt_none]`, `[reconcile_query_failed]`, `[reconcile_manual_required]`, `[reconcile_exception]`, `[vix_unavailable]` (day init).

**Stable `PauseReason` codes** (also in Telegram `/status` when paused)

| Code | Typical cause |
|------|----------------|
| `reconcile_query_failed` | `position_list_query` returned error — OpenD/API/trd_env |
| `reconcile_manual_required` | Open broker positions but `FABIO_AUTO_ADOPT_OPEN_POSITIONS=0` |
| `reconcile_auto_adopt_none` | Auto-adopt on but zero positions adopted (often missing option cost_basis / bad code / duplicate symbol) |
| `reconcile_exception` | Unexpected error during reconcile path |
| `vix_unavailable` | Day init blocked — VIX feed returned nothing |
| `manual_operator` | Telegram `/pause` |

**Recovery order (recommended)**

1. Read `/status` (or stdout): `PauseReason`, `PauseHint`, and pending unreconciled symbols.
2. In Moomoo, confirm real open qty and that option rows expose a positive **`cost_price` / `average_cost` / `avg_price`** for each adopted contract (auto-adopt needs a valid option premium basis).
3. If inventory should be flat, close or roll in the market so the broker shows **no positive-qty** orphans, then restart.
4. If you intentionally run with manual adoption only, set `FABIO_AUTO_ADOPT_OPEN_POSITIONS=0` knowing the bot **pauses** while orphans exist; otherwise keep `1` after validating broker data.
5. `/resume` clears the pause flag and Telegram pause metadata but **does not fix** bad broker basis; restart after fixing data so startup adopt succeeds.

See also: [docs/Morning-Audit.md](docs/Morning-Audit.md) (preflight + triage), [docs/audit-runbook.md](docs/audit-runbook.md) (broker vs Sheets inventory).

### Moomoo-authoritative sync audit

Read-only audit checks (dry-run -> normal -> EOD):

```bash
python3 scripts/audit_moomoo_sync.py --dry-run --lookback-min 180
python3 scripts/audit_moomoo_sync.py --lookback-min 180
python3 scripts/audit_moomoo_sync.py --eod --lookback-min 480
```

Summarize audit artifacts:

```bash
bash scripts/summarize_audit_sync.sh audit_sync.jsonl
```

Sync audit references:
- `docs/audit-sync-spec.md`
- `docs/audit-runbook.md`

### EOD operational sequence (safe order)

Use this sequence after market-close workflows:

```bash
# 1) Confirm bot health snapshot / no pressure issues
python3 verify_phase2_reliability.py

# 2) Reconcile broker -> canonical tabs (dry-run then publish)
python3 reconcile_moomoo_to_sheets.py --dry-run
python3 reconcile_moomoo_to_sheets.py

# 3) Run EOD sync audit confirmation
python3 scripts/audit_moomoo_sync.py --eod --lookback-min 480

# 4) Review audit summary
bash scripts/summarize_audit_sync.sh audit_sync.jsonl
```

### Scheduler lifecycle (bot + sync audit)

Install bot weekday scheduler:

```bash
bash install_fabio_scheduler.sh
```

Install sync-audit schedulers (15m + EOD):

```bash
bash install_sync_audit_scheduler.sh
```

Verify launchd jobs are loaded:

```bash
launchctl print "gui/$(id -u)/com.claytonorb.fabio"
launchctl print "gui/$(id -u)/com.claytonorb.fabio.syncaudit.15m"
launchctl print "gui/$(id -u)/com.claytonorb.fabio.syncaudit.eod"
```

Run scheduler smoke tests now (without waiting for trigger times):

```bash
launchctl start com.claytonorb.fabio
bash scripts/run_moomoo_sync_audit.sh
bash scripts/run_moomoo_sync_audit.sh --eod
```

Uninstall schedulers:

```bash
launchctl unload ~/Library/LaunchAgents/com.claytonorb.fabio.plist && rm ~/Library/LaunchAgents/com.claytonorb.fabio.plist
launchctl unload ~/Library/LaunchAgents/com.claytonorb.fabio.syncaudit.15m.plist && rm ~/Library/LaunchAgents/com.claytonorb.fabio.syncaudit.15m.plist
launchctl unload ~/Library/LaunchAgents/com.claytonorb.fabio.syncaudit.eod.plist && rm ~/Library/LaunchAgents/com.claytonorb.fabio.syncaudit.eod.plist
```

### Guarded actions (high impact)

Stop bot process manually (use only when scheduler/controls are insufficient):

```bash
pkill -f orb_bot_fabio.py
```

Push dashboard to GitHub Pages (optional publish path):

```bash
bash push_dashboard.sh
```

### Incident triage quick paths

Reconcile mismatch investigation loop:

```bash
python3 reconcile_moomoo_to_sheets.py --dry-run
python3 scripts/audit_moomoo_sync.py --lookback-min 480 --dry-run
bash scripts/summarize_audit_sync.sh audit_sync.jsonl
```

Tail scheduler/audit logs:

```bash
tail -f audit_sync_scheduler.log
```

### Maintenance and quality

Install/update dependencies:

```bash
pip install -r requirements-dev.txt
pip install -r requirements-optional.txt
```

(`requirements-dev.txt` pulls in `requirements.txt`; add `requirements-optional.txt` when using Sheets.)

Syntax checks:

```bash
python3 -m py_compile orb_bot_fabio.py
python3 -m py_compile scripts/audit_moomoo_sync.py
```

Targeted tests and full tests:

```bash
python3 -m pytest tests/test_audit_moomoo_sync.py -q
python3 -m pytest tests/ -v
```

Secrets scan hooks:

```bash
pre-commit install
pre-commit run --all-files
```

**Note:** launchd jobs run with minimal environment (`PATH=/usr/bin:/bin:/usr/sbin:/sbin`). Keep interpreter paths and env assumptions explicit.

---

## Troubleshooting

- **`No matching distribution for moomoo`:** The PyPI package is **`moomoo-api`** (`import moomoo` unchanged). Use `requirements.txt` as written.
- **`yfinance not found`:** Run the `pip install` line above.
- **Polygon rate limits / slow runs:** The script sleeps between paginated requests (`POLYGON_SLEEP_SEC`). Expect long runs for multi-symbol, multi-year history.
- **No trades:** Tighten filters in CONFIG, shorten the date range, or confirm data loaded (empty intraday → no signals).
- **Reconcile mismatch alert (`RECONCILE_MISMATCH`):** Broker open positions and computed `Open Inventory` disagree. **Both** `trade_data.json`/HTML refresh and canonical Sheets tab replaces are skipped. Re-run reconcile after fixing Moomoo/FIFO inventory visibility, then publish again.

---

## License / use

Use at your own risk. Verify all rules and parameters against your own trading plan before relying on any automation.

## Repo hygiene

- Use `.gitignore` to exclude secrets and generated outputs (`.env`, credentials JSON, logs, generated CSV/PNG).
- **Before your first `git commit`:** run `git init` (if needed), then `git status` and confirm nothing sensitive or machine-local appears (e.g. `trade_data.json`, logs). Add patterns to `.gitignore` if you introduce new local-only stores.
- Install local secret scanning hooks:
  ```bash
  pip install -r requirements-dev.txt
  pre-commit install
  pre-commit run --all-files
  ```
- CI now enforces a secret scan (`.github/workflows/secret-scan.yml`) on push/PR.
- If exposure is suspected, follow `SECURITY_RUNBOOK.md` immediately (revoke/rotate first, then verify scans).
- Phase 2 architecture note for exit-timeframe parity is tracked in `PHASE2_EXIT_TIMEFRAME_DECISION.md`.
- Keep plaintext secrets out of this directory; use `.env.example` and `FABIO_ENV_FILE` for externalized secret paths.
- Runtime telemetry retention:
  - `bot_health_snapshots.jsonl` is local-only and auto-pruned to recent history by the bot.
  - Keep logs/artifacts local and rotate/delete older operational files on a schedule.
- If you need Google Sheets setup docs, check `../orb_bot/GOOGLE_SETUP.md` from this folder path.
- Dependency files:
  - `requirements.txt` (core runtime, pinned)
  - `requirements.lock` (full `pip freeze` after core install — optional stricter reproducibility)
  - `requirements-optional.txt` (Google Sheets extras, pinned)
  - `requirements-dev.txt` (pytest, pre-commit, etc.; includes `requirements.txt` via `-r`)

## Architecture visual

- See `ARCHITECTURE.md` for the system architecture and trading-day workflow diagrams.
- Runtime sessions are evaluated in `America/New_York`; keep host clock synchronized.
