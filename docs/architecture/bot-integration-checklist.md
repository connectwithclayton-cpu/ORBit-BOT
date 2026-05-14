# Bot integration checklist (external strategy repo)

Use this for a **main trading bot** that lives **outside** [this repository](../../README.md) (for example a project with `signals.py`, `risk.py`, `execution.py`, schedulers). Check items as you wire or audit behavior. Goal: **narrow pipelines**, **API / OpenD discipline**, clean hand-off to the **Moomoo fail-safe** in this repo.

## How this repo fits in

| Here (Fabio / ORBit repo root) | Your bot repo |
|------------------------|---------------|
| [`moomoo_eod_failsafe.py`](../../backend/moomoo_eod_failsafe.py) — post–EOD broker sweep | Primary **3:45 PM ET** (or your) close logic |
| Architecture docs under `docs/architecture/` | Strategy, execution, logging, your `README` |

Record your bot path in [architecture-system-context.md](architecture-system-context.md).

---

## 1. Narrow pipelines (alpha / truth / safety)

Reference: [architecture-narrow-pipelines.md](architecture-narrow-pipelines.md).

- [ ] **Signals** compute intents without blocking on the broker when avoidable (features/decisions first).
- [ ] **Risk** gates intents using **cached** or **low-frequency** position / exposure state where possible—not a full broker poll every tick.
- [ ] **Execution** is a **thin** layer: translate approved intents → orders; retries / idempotency live here or in one dedicated module.
- [ ] **Reconciliation** updates authoritative state on a **timer**, on **fills**, or in a **dedicated loop**—not inside every signal evaluation.
- [ ] **Safety / EOD fail-safe** is a **separate process or job** from the main loop; it does not replace your primary close. See [scheduling](architecture-scheduling-time-semantics.md).

---

## 2. API and rate discipline (Moomoo / OpenD)

Reference: [architecture-api-rate-discipline.md](architecture-api-rate-discipline.md), [architecture-opend-shared-dependency.md](architecture-opend-shared-dependency.md).

- [ ] OpenD treated as a **shared gateway**: supervise uptime; expect **one** gateway for typical setups.
- [ ] No **`position_list_query`** (or equivalent) on **every** bar/tick unless required; batch or cache non-critical reads.
- [ ] Multiple closes in a short window are **paced** (delays or batches) if the broker throttles.
- [ ] Emergency flatten in **this** repo uses **`--scope options`** by default; widen to **`all`** only on purpose so you do not liquidate unrelated holdings.

---

## 3. Scheduling and non-interference

Reference: [architecture-scheduling-time-semantics.md](architecture-scheduling-time-semantics.md).

- [ ] **Primary EOD** (e.g. **3:45 PM ET**) runs as its **own** scheduled job or strategy rule set.
- [ ] **Fail-safe** ([`moomoo_eod_failsafe.py`](../../backend/moomoo_eod_failsafe.py)) runs **minutes later** (e.g. **~3:50 PM ET**), **separate** job, with `--require-after-et` aligned to your cutoff.
- [ ] Fail-safe is **not** started from inside the primary EOD routine in a way that blocks or replaces it.
- [ ] Later jobs (reports, dashboards) do **not** wrongly depend on the fail-safe completing inside the same script as primary EOD.

---

## 4. Idempotency and observability

Reference: [architecture-idempotency-eod-flatten.md](architecture-idempotency-eod-flatten.md), [architecture-observability.md](architecture-observability.md).

- [ ] Bot logs include **timestamps** and enough context to trace **why** an order was sent (symbol, side, qty, reason / strategy tag).
- [ ] Prefer **structured logs** (e.g. JSONL) or a consistent format so you can grep / `jq` for incidents.
- [ ] You know [fail-safe **exit codes**](../../README.md#exit-codes-moomoo_eod_failsafepy): especially **`3`** (partial `place_order` failures) and **`4`** (ET guard skip).
- [ ] Optional: append fail-safe JSONL and use [`scripts/summarize_failsafe_jsonl.sh`](../../scripts/summarize_failsafe_jsonl.sh) or the observability **jq** appendix.

---

## 5. Policy and risk (no exercise)

- [ ] Strategy and automation **close in the market** (sell to close / buy to close) or roll; **no intentional exercise** path for listed options (see [.cursor/rules/no-contract-exercise.mdc](../../.cursor/rules/no-contract-exercise.mdc) for AI-assisted work in this workspace).

---

## 6. Repository hygiene (your bot repo)

Reference: [architecture-repository-hygiene.md](architecture-repository-hygiene.md).

- [ ] Bot repo has a **README** with: how to start/stop, where logs go, and how EOD relates to the fail-safe repo (link optional).
- [ ] **Secrets** (`.env`, API keys) are gitignored; only **variable names** appear in docs.
- [ ] If you add a **monorepo** later, keep one runbook entry point (link children READMEs).

---

## Quick map: modules (example naming)

Your filenames may differ; assign each concern explicitly:

| Concern | Example modules |
|---------|-----------------|
| Alpha | `signals.py`, strategy / `orb_bot.py` |
| Risk | `risk.py` |
| Execution | `execution.py` |
| Truth / ops | reconcile loop, `sheets_logger.py`, internal state |
| Safety (broker) | `moomoo_eod_failsafe.py` **in this repo** + your scheduler |

---

## See also

- [System context](architecture-system-context.md)  
- [README — runbook](../../README.md)  
