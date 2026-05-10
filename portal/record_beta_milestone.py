#!/usr/bin/env python3
"""
Append the current git identity to ``beta_manifest.json`` as a new milestone row.
Keeps the newest 3 records (history is tracked in git — commit after updating).

Usage (from Fabio_bot root):

    python3 portal/record_beta_milestone.py [optional note ...]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_PORTAL = Path(__file__).resolve().parent
_FABIO_ROOT = _PORTAL.parent
sys.path.insert(0, str(_FABIO_ROOT / "backend"))

from fabio_beta_identity import get_git_identity, load_beta_manifest_records

_MANIFEST = _PORTAL / "beta_manifest.json"
_MAX = 3


def main() -> None:
    ap = argparse.ArgumentParser(description="Record a beta milestone in beta_manifest.json")
    ap.add_argument(
        "note",
        nargs="*",
        default=[],
        help="Optional note stored with this milestone",
    )
    args = ap.parse_args()
    note = " ".join(args.note).strip() or None

    gi = get_git_identity(_FABIO_ROOT)
    short = gi.get("git_short") or "unknown"
    branch = gi.get("branch") or "unknown"
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    new_row = {
        "recorded_at_utc": ts,
        "git_short": short,
        "git_branch": branch,
        **({"note": note} if note else {}),
    }

    existing = load_beta_manifest_records(_PORTAL)
    combined = [new_row] + existing
    seen_keys: set[tuple[str | None, str | None]] = set()
    out: list[dict] = []
    for r in combined:
        k = (str(r.get("git_short") or ""), str(r.get("recorded_at_utc") or ""))
        if k in seen_keys:
            continue
        seen_keys.add(k)
        out.append(r)
        if len(out) >= _MAX:
            break

    payload = {
        "schema_version": 1,
        "channel": "beta",
        "description": (
            "Rolling beta milestones (newest first), max 3 rows — committed for audit. "
            "Update with: python3 portal/record_beta_milestone.py"
        ),
        "records": out,
    }
    _MANIFEST.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {_MANIFEST} ({len(out)} record(s))")
    print(f"  {new_row}")


if __name__ == "__main__":
    main()
