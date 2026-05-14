# Repository and workflow hygiene (Cursor / Git)

Treat **one** repository or **monorepo folder** as the **source of truth** for automation you rely on at EOD—not just strategy code.

## Checklist — workflow Section 7

1. **Single source of truth** — Track **fail-safe version** (Git), **environment variable checklist**, and a **runbook** in-repo so a new machine or teammate can reproduce operations without DMs.
2. **Pin dependencies** — Lock **SDK** versions (e.g. [`requirements-moomoo.txt`](../../backend/requirements-moomoo.txt)) and record **OpenD** install expectations (build/channel, not necessarily the same semver as the Python package—see Moomoo’s OpenAPI release notes).
3. **README runbook** — Minimal ops doc: **how to dry-run the fail-safe**, **what `MOOMOO_*` variables mean**, and **who to call / what to check if flatten fires** (on-call, Slack channel, or yourself with a post-incident checklist).

## What belongs in this repo

| Asset | Purpose |
|-------|---------|
| [`moomoo_eod_failsafe.py`](../../backend/moomoo_eod_failsafe.py) | Versioned fail-safe behavior |
| [`requirements-moomoo.txt`](../../backend/requirements-moomoo.txt) | Pinned `moomoo-api` (same version as `backend/requirements.txt` for one-venv installs) |
| [README.md](../../README.md) | Operational runbook at repo root |
| [`docs/architecture`](.) | Architecture and policy (system context, pipelines, scheduling, idempotency, observability, API discipline) |
| [`scripts/`](../../scripts/) | Optional helpers (e.g. JSONL summarize) |

When **bot code** lands next to the fail-safe, keep **one** README or link from README to the bot’s own `README` so onboarding does not split across unlinked folders.

## OpenD and SDK compatibility

- Install **OpenD** from [Moomoo OpenAPI](https://openapi.moomoo.com/) for your **region**.
- Use a **moomoo-api** (Python SDK) **major.minor** that matches what Moomoo documents for your OpenD generation; if upgrades break RPC behavior, upgrade **OpenD + SDK** together per vendor guidance.
- After upgrades, run **`python3 backend/moomoo_eod_failsafe.py --dry-run`** (from this repository root) and confirm connectivity before scheduling live flatten.

## Git hygiene

- **Tag** or **release notes** when changing fail-safe semantics (scope, timing guards, order logic).
- Avoid **secrets** in Git: use env vars or a local-only `.env` (gitignored); document variable **names** only in the runbook.

See also: [README.md](../../README.md), [System context](architecture-system-context.md), [Bot integration checklist](bot-integration-checklist.md), [API and rate discipline](architecture-api-rate-discipline.md), [Observability](architecture-observability.md).
