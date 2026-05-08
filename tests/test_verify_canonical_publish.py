from __future__ import annotations

import json
from pathlib import Path

from verify_canonical_publish import audit_jsonl_gate_failures


def test_gate_ok_skip_status(tmp_path: Path):
    j = tmp_path / "a.jsonl"
    j.write_text(json.dumps({"ts": "2099-01-01T12:00:00+00:00", "status": "SKIP"}) + "\n")
    assert audit_jsonl_gate_failures(j) == []


def test_gate_ok_pass_status(tmp_path: Path):
    j = tmp_path / "a.jsonl"
    j.write_text(json.dumps({"ts": "2099-01-01T12:00:00+00:00", "status": "PASS"}) + "\n")
    assert audit_jsonl_gate_failures(j) == []


def test_gate_fail_on_error(tmp_path: Path):
    j = tmp_path / "a.jsonl"
    j.write_text(json.dumps({"ts": "2099-01-01T12:00:00+00:00", "status": "ERROR"}) + "\n")
    assert audit_jsonl_gate_failures(j)


def test_gate_missing_file(tmp_path: Path):
    assert audit_jsonl_gate_failures(tmp_path / "nope.jsonl")
