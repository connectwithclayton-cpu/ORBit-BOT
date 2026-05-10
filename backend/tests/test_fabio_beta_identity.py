"""fabio_beta_identity: manifest load and payload shape."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fabio_beta_identity import beta_identity_payload, load_beta_manifest_records


def test_load_beta_manifest_reads_records(tmp_path: Path) -> None:
    mf = tmp_path / "beta_manifest.json"
    mf.write_text(
        json.dumps(
            {
                "records": [
                    {"git_short": "aaa", "recorded_at_utc": "2026-01-01T00:00:00Z"},
                    {"git_short": "bbb", "recorded_at_utc": "2026-01-02T00:00:00Z"},
                ]
            }
        ),
        encoding="utf-8",
    )

    recs = load_beta_manifest_records(tmp_path)
    assert len(recs) == 2
    assert recs[0]["git_short"] == "aaa"


def test_beta_identity_payload_has_expected_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fabio_beta_identity as m

    monkeypatch.setattr(
        m,
        "get_git_identity",
        lambda _b=None: {
            "git_short": "test12",
            "branch": "main",
            "dirty": False,
            "describe": "test12",
        },
    )
    monkeypatch.setattr(m, "load_beta_manifest_records", lambda _b=None: [])

    p = beta_identity_payload(tmp_path)
    assert p["channel"] == "beta"
    assert p["badge_label"] == "BETA · test12"
    assert p["running_git_short"] == "test12"
    assert p["manifest_records"] == []
