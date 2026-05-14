"""
Git-tied beta channel metadata for dashboards and debug views.

Committed history lives in ``beta_manifest.json`` (rolling last 3 milestones).
Runtime identity comes from ``git`` when available (short SHA, branch, dirty).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

_MANIFEST_NAME = "beta_manifest.json"
_MAX_MANIFEST_RECORDS = 3


def _git_cwd(base: Path | None) -> Path:
    if base is not None:
        return base.resolve()
    from fabio_bot_paths import fabio_bot_root

    return fabio_bot_root()


def _manifest_dir(base: Path | None) -> Path:
    if base is not None:
        return base.resolve()
    from fabio_bot_paths import fabio_bot_root

    return fabio_bot_root() / "portal"


def get_git_identity(base: Path | None = None) -> dict[str, Any]:
    """Return short SHA, branch, dirty flag; tolerate missing git or shallow clones."""
    root = _git_cwd(base)
    out: dict[str, Any] = {
        "git_short": None,
        "branch": None,
        "dirty": False,
        "describe": None,
    }

    def _run(args: list[str]) -> str | None:
        try:
            r = subprocess.run(
                args,
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=4,
            )
            if r.returncode == 0:
                return r.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass
        return None

    out["git_short"] = _run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"])
    out["branch"] = _run(["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"])
    ds = _run(["git", "-C", str(root), "describe", "--always", "--dirty"])
    out["describe"] = ds
    out["dirty"] = bool(ds and ds.endswith("-dirty"))
    return out


def load_beta_manifest_records(base: Path | None = None) -> list[dict[str, Any]]:
    """Load ``records`` from committed ``beta_manifest.json`` (max 3 in file)."""
    path = _manifest_dir(base) / _MANIFEST_NAME
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    recs = raw.get("records")
    if not isinstance(recs, list):
        return []
    out: list[dict[str, Any]] = []
    for item in recs[:_MAX_MANIFEST_RECORDS]:
        if isinstance(item, dict):
            out.append(dict(item))
    return out


def beta_identity_payload(base: Path | None = None) -> dict[str, Any]:
    """
    Payload for embedding in dashboard / debug board JSON.

    ``manifest_records`` are git-tracked milestones (newest first).
    ``running_*`` reflect the working tree at HTML generation time.

    When ``base`` is set (e.g. in tests), it is used for both git cwd and manifest
    directory. When omitted, git uses ``fabio_bot_root()`` and manifest is read
    from ``portal/beta_manifest.json``.
    """
    gi = get_git_identity(base)
    records = load_beta_manifest_records(base)
    return {
        "channel": "beta",
        "running_git_short": gi.get("git_short"),
        "running_branch": gi.get("branch"),
        "running_dirty": gi.get("dirty"),
        "running_describe": gi.get("describe"),
        "badge_label": "BETA",
        "manifest_records": records,
        "manifest_path": _MANIFEST_NAME,
        "max_manifest_slots": _MAX_MANIFEST_RECORDS,
    }
