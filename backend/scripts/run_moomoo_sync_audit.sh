#!/usr/bin/env bash
# Lightweight wrapper for sync audit runner.
# Uses lock + jitter + timeout to avoid overlap/interference.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FABIO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$(which python3)}"
AUDIT_PY="${FABIO_ROOT}/backend/scripts/audit_moomoo_sync.py"
LOG_JSONL="${FABIO_ROOT}/audit_sync.jsonl"
STATE_JSON="${FABIO_ROOT}/audit_sync_state.json"
LOCK_DIR="${FABIO_ROOT}/.audit_sync.lock"
export PYTHONPATH="${FABIO_ROOT}/backend:${FABIO_ROOT}/frontend"
RUNTIME_BUDGET_SEC="${RUNTIME_BUDGET_SEC:-20}"
LOOKBACK_MIN="${LOOKBACK_MIN:-180}"
ALERT_AFTER_FAILURES="${ALERT_AFTER_FAILURES:-2}"
JITTER_MAX_SEC="${JITTER_MAX_SEC:-8}"

cd "$FABIO_ROOT"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "python3 not executable: $PYTHON_BIN" >&2
  exit 2
fi

if [[ ! -f "$AUDIT_PY" ]]; then
  echo "audit script not found: $AUDIT_PY" >&2
  exit 2
fi

EOD_FLAG=""
if [[ "${1:-}" == "--eod" ]]; then
  EOD_FLAG="--eod"
fi

if [[ -n "$EOD_FLAG" ]]; then
  if ! "$PYTHON_BIN" -m fabio_live.calendar_gate should-run-sync-audit-eod; then
    exit 0
  fi
else
  if ! "$PYTHON_BIN" -m fabio_live.calendar_gate should-run-sync-audit-intraday; then
    exit 0
  fi
fi

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  # Existing run still active; skip this cycle to prevent pressure.
  exit 0
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

# Timeout guard ensures the audit cannot block other system activities.
AUDIT_STATUS=0
set +o errexit
if command -v timeout >/dev/null 2>&1; then
  timeout "${RUNTIME_BUDGET_SEC}" "$PYTHON_BIN" "$AUDIT_PY" \
    --lookback-min "$LOOKBACK_MIN" \
    --jsonl "$LOG_JSONL" \
    --state-file "$STATE_JSON" \
    --max-runtime-sec "$RUNTIME_BUDGET_SEC" \
    --alert-after-failures "$ALERT_AFTER_FAILURES" \
    --jitter-max-sec "$JITTER_MAX_SEC" \
    $EOD_FLAG
  AUDIT_STATUS=$?
else
  "$PYTHON_BIN" "$AUDIT_PY" \
    --lookback-min "$LOOKBACK_MIN" \
    --jsonl "$LOG_JSONL" \
    --state-file "$STATE_JSON" \
    --max-runtime-sec "$RUNTIME_BUDGET_SEC" \
    --alert-after-failures "$ALERT_AFTER_FAILURES" \
    --jitter-max-sec "$JITTER_MAX_SEC" \
    $EOD_FLAG
  AUDIT_STATUS=$?
fi
set -o errexit

if [[ -n "$EOD_FLAG" && "$AUDIT_STATUS" -eq 0 ]]; then
  "$PYTHON_BIN" -m fabio_live.calendar_gate stamp-sync-audit-eod || true
fi
exit "${AUDIT_STATUS}"
