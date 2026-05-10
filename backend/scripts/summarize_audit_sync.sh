#!/usr/bin/env bash
# Summarize audit_sync JSONL logs.
# Usage:
#   ./scripts/summarize_audit_sync.sh [jsonl_file]

set -euo pipefail

FILE="${1:-audit_sync.jsonl}"
if [[ ! -f "$FILE" ]]; then
  echo "File not found: $FILE" >&2
  exit 1
fi

if command -v jq >/dev/null 2>&1; then
  echo "=== audit summary ($FILE) ==="
  jq -r '
    def status(x): x.status // "UNKNOWN";
    def sev(x): x.severity // "UNKNOWN";
    ([.] + [inputs]) as $rows
    | "total_runs=\($rows|length)",
      "pass_runs=\($rows|map(select(status(.)=="PASS"))|length)",
      "fail_runs=\($rows|map(select(status(.)=="FAIL"))|length)",
      "error_runs=\($rows|map(select(status(.)=="ERROR"))|length)",
      "last_status=\(($rows|last|status(.)) // "n/a")",
      "last_severity=\(($rows|last|sev(.)) // "n/a")",
      "last_ts=\(($rows|last|.ts) // "n/a")"
  ' "$FILE"
  echo
  echo "Top drift failure tags:"
  jq -r '
    ([.] + [inputs] | map(.drift.failures[]?)) | group_by(.) | map({k:.[0], c:length}) | sort_by(-.c)[:10] |
    .[] | "\(.c)\t\(.k)"
  ' "$FILE" || true
else
  echo "jq not found; basic tail summary:"
  python3 - "$FILE" <<'PY'
import json, sys
from collections import Counter
path = sys.argv[1]
rows = []
with open(path, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            pass
print(f"total_runs={len(rows)}")
status = Counter(r.get("status","UNKNOWN") for r in rows)
print(f"pass_runs={status.get('PASS',0)}")
print(f"fail_runs={status.get('FAIL',0)}")
print(f"error_runs={status.get('ERROR',0)}")
if rows:
    last = rows[-1]
    print(f"last_status={last.get('status','n/a')}")
    print(f"last_severity={last.get('severity','n/a')}")
    print(f"last_ts={last.get('ts','n/a')}")
PY
fi
