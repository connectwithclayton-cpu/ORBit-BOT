#!/usr/bin/env bash
# Lightweight wrapper for sync audit runner.
# Uses lock + jitter + timeout to avoid overlap/interference.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FABIO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
_resolve_python_bin() {
  if [[ -n "${PYTHON_BIN:-}" && -x "${PYTHON_BIN}" ]]; then
    echo "$PYTHON_BIN"
    return 0
  fi

  local candidate
  for candidate in \
    "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3" \
    "$(command -v python3 2>/dev/null || true)" \
    "/usr/local/bin/python3" \
    "/opt/homebrew/bin/python3" \
    "/usr/bin/python3"; do
    [[ -n "$candidate" && -x "$candidate" ]] || continue
    if "$candidate" -c "import pandas" >/dev/null 2>&1; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}
PYTHON_BIN="${PYTHON_BIN:-$(_resolve_python_bin || true)}"
AUDIT_PY="${FABIO_ROOT}/backend/scripts/audit_moomoo_sync.py"
LOG_JSONL="${FABIO_ROOT}/audit_sync.jsonl"
STATE_JSON="${FABIO_ROOT}/audit_sync_state.json"
LOCK_DIR="${FABIO_ROOT}/.audit_sync.lock"
export PYTHONPATH="${FABIO_ROOT}/backend:${FABIO_ROOT}/frontend"
RUNTIME_BUDGET_SEC="${RUNTIME_BUDGET_SEC:-20}"
LOOKBACK_MIN="${LOOKBACK_MIN:-180}"
ALERT_AFTER_FAILURES="${ALERT_AFTER_FAILURES:-2}"
JITTER_MAX_SEC="${JITTER_MAX_SEC:-8}"
FABIO_AUDIT_TRUST_FIFO_IF_BROKER_QUERY_EMPTY="${FABIO_AUDIT_TRUST_FIFO_IF_BROKER_QUERY_EMPTY:-1}"
export FABIO_AUDIT_TRUST_FIFO_IF_BROKER_QUERY_EMPTY

cd "$FABIO_ROOT"

# Load the same external secrets file used by the live bot so SheetsLogger can
# connect when launchd starts with a minimal environment.
# shellcheck source=../../portal/fabio_env.sh
source "${FABIO_ROOT}/portal/fabio_env.sh"
if fabio_resolve_env_file "$FABIO_ROOT" && [[ -n "${FABIO_ENV_FILE:-}" && -f "$FABIO_ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$FABIO_ENV_FILE"
  set +a
fi

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
