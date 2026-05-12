#!/usr/bin/env bash
# launchd helper: skip starting the live bot on NYSE closed days (holidays / weekends
# are never trading days in XNYS). See portal/docs/EXCHANGE_CALENDAR.md.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="${ROOT}/backend:${ROOT}/frontend"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
LOG="${ROOT}/orb_bot_fabio.log"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "python3 not executable: $PYTHON_BIN" >&2
  exit 2
fi

if ! "$PYTHON_BIN" -m fabio_live.calendar_gate should-start-bot >>"$LOG" 2>&1; then
  {
    echo ""
    echo "$(date '+%Y-%m-%d %H:%M:%S %Z') [launchd] Skipped Fabio start (NYSE calendar: not a trading day)."
  } >>"$LOG"
  exit 0
fi

exec "$PYTHON_BIN" "$ROOT/backend/orb_bot_fabio.py"
