# Security Incident and Credential Rotation Runbook

This runbook is for suspected or confirmed credential exposure in this project.

## 1) Trigger Conditions

Execute this runbook immediately if any of the following occur:
- A secret file (`.env`, `google_credentials.json`, other credential JSON) is committed, pushed, or shared.
- A token/key appears in logs, screenshots, chat exports, or issue comments.
- A workstation with local credentials is lost/compromised.

## 2) Immediate Containment (first 15 minutes)

1. Stop automation:
   - Pause the bot (`/pause`) and stop local process if needed.
2. Revoke exposed credentials:
   - Moomoo/OpenAPI keys
   - Telegram bot token
   - Google service-account key (if used)
   - Polygon API key (if present)
3. Invalidate leaked artifacts:
   - Delete leaked files from shared channels/storage.
   - Remove exposed snippets from tickets/docs where possible.

## 3) Rotation Procedure

1. Generate new credentials for each affected integration.
2. Update local secret storage only:
   - Preferred: external env file + `FABIO_ENV_FILE` path outside repo.
   - `.env` in repo root only as temporary local fallback.
   - Replace `google_credentials.json` with newly issued key stored outside repo root.
3. Restart dependencies/services that cache credentials.
4. Validate auth with a pre-flight run:
   - `PYTHONPATH=backend:frontend python3 backend/print_effective_config.py` (from `Fabio_bot/` root)
   - Confirm live mode safety output is correct (`SIMULATE` vs `REAL`).

## 4) Repository Hygiene and Verification

1. Ensure `.gitignore` still excludes secret files and key material.
2. Run secret scan locally:
   - `pre-commit run -c portal/tooling/pre-commit-config.yaml --all-files`
3. Confirm CI secret scan passes on PR/push.
4. If a secret was committed in history, rewrite history and rotate again.

## 5) Post-Incident Review (same day)

Record:
- What leaked, where, and duration of exposure.
- What was rotated and when.
- Validation evidence (scan output, CI pass, bot startup checks).
- Follow-up hardening tasks (new ignores, alerts, process changes).

## 6) Prevention Checklist (ongoing)

- Keep secret files local only and out of cloud-synced/public paths.
- Never paste tokens into terminal history, docs, or screenshots.
- Require secret scanning pre-commit and in CI for every PR.
- Re-rotate high-risk credentials on a regular cadence.
- Keep runtime telemetry local with retention (logs, snapshots, trade state files).
