#!/usr/bin/env python3
"""
Optional gate: inspect the tail of `audit_sync.jsonl` (scripts/audit_moomoo_sync.py output).

Fails on last event status ERROR/FAIL unless --warn-only.

Also exposed as audit_jsonl_gate_failures() for verify_phase2_reliability.py.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def _load_last_jsonl_object(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    last_line = ""
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                last_line = line
    except OSError:
        return None
    if not last_line:
        return None
    try:
        return json.loads(last_line)
    except json.JSONDecodeError:
        return None


def _age_minutes(ts: str) -> float:
    dt = datetime.fromisoformat(ts)
    now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
    return max(0.0, (now - dt).total_seconds() / 60.0)


def audit_jsonl_gate_failures(
    jsonl_path: Path,
    *,
    max_age_min: float | None = None,
) -> list[str]:
    """
    Returns human-readable failure reasons; empty means OK for pre-open use.
    """
    ev = _load_last_jsonl_object(jsonl_path)
    out: list[str] = []
    if ev is None:
        out.append(f"sync audit JSONL missing or unreadable: {jsonl_path}")
        return out
    status = str(ev.get("status", "")).upper()
    severity = str(ev.get("severity", "")).upper()
    if status in {"FAIL", "ERROR"}:
        out.append(f"sync_audit status={status} severity={severity} (see {jsonl_path})")
    ts = str(ev.get("ts", ""))
    if ts and max_age_min is not None and max_age_min >= 0:
        try:
            if _age_minutes(ts) > max_age_min:
                out.append(
                    f"sync_audit record stale ({_age_minutes(ts):.0f}m > {max_age_min}m): {jsonl_path}"
                )
        except Exception:
            out.append(f"sync_audit bad timestamp ts={ts!r}")
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Gate on last sync audit JSONL entry")
    p.add_argument(
        "--jsonl",
        type=Path,
        default=Path("audit_sync.jsonl"),
        help="Append-only audit log (default: ./audit_sync.jsonl)",
    )
    p.add_argument(
        "--max-age-min",
        type=float,
        default=-1,
        help="Fail if newest record older than N minutes (-1 disables age check)",
    )
    args = p.parse_args()
    max_age = None if args.max_age_min < 0 else float(args.max_age_min)
    fails = audit_jsonl_gate_failures(Path(args.jsonl), max_age_min=max_age)
    if fails:
        for x in fails:
            print(f"FAIL: {x}")
        return 1
    print(f"PASS: sync audit gate OK ({args.jsonl})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
