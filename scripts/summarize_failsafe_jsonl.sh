#!/usr/bin/env bash
# Summarize moomoo_eod_failsafe JSONL (one JSON object per line).
# Usage:
#   ./scripts/summarize_failsafe_jsonl.sh [file]
#   grep '^{' eod_failsafe.jsonl | ./scripts/summarize_failsafe_jsonl.sh
# Requires: jq

set -euo pipefail

if ! command -v jq >/dev/null 2>&1; then
  echo "jq not found; install jq or use recipes in docs/architecture/architecture-observability.md" >&2
  exit 1
fi

if [[ -n "${1:-}" && "$1" != "-" ]]; then
  INPUT=$(grep '^{' "$1" || true)
else
  INPUT=$(grep '^{' || true)
fi

if [[ -z "${INPUT// /}" ]]; then
  echo "No JSON lines found."
  exit 0
fi

echo "=== Events (count) ==="
echo "$INPUT" | jq -r '.event // "unknown"' | sort | uniq -c | sort -nr

echo ""
echo "=== place_order_end by reason_code ==="
echo "$INPUT" | jq -r 'select(.event == "place_order_end") | .reason_code // "null"' | sort | uniq -c | sort -nr

echo ""
echo "=== Last run_complete ==="
echo "$INPUT" | jq -c 'select(.event == "run_complete")' | tail -n 1

fail_n=$(echo "$INPUT" | jq -r 'select(.event == "place_order_end" and .reason_code != "ok") | .symbol' | wc -l | tr -d ' ')
echo ""
echo "=== Summary ==="
echo "Non-OK place_order_end rows: $fail_n"
