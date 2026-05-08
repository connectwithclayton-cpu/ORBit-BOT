"""Output-path guardrails for backtest runs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class BacktestOutputPaths:
    files: dict[str, Path]
    metadata: Path
    run_id: str
    output_dir: Path
    diverted_from_root: bool


def _utc_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def resolve_output_paths(
    repo_root: Path,
    run_label: str,
    default_names: Mapping[str, str],
    output_dir: str | Path | None = None,
) -> BacktestOutputPaths:
    """
    Preserve root-level filenames for first runs, but never overwrite them.

    If any default output already exists, all artifacts for the new run are
    diverted to results/<run_label>/<run_id>/.
    """
    root = Path(repo_root)
    run_id = _utc_run_id()
    defaults = {key: root / name for key, name in default_names.items()}
    root_collision = any(path.exists() for path in defaults.values())

    if output_dir is not None:
        out_dir = Path(output_dir)
        if not out_dir.is_absolute():
            out_dir = root / out_dir
        diverted = out_dir.resolve() != root.resolve()
    elif root_collision:
        out_dir = root / "results" / run_label / run_id
        diverted = True
    else:
        out_dir = root
        diverted = False

    out_dir.mkdir(parents=True, exist_ok=True)
    files = {key: out_dir / name for key, name in default_names.items()}
    metadata = out_dir / f"{run_label}_run_metadata.json"
    return BacktestOutputPaths(
        files=files,
        metadata=metadata,
        run_id=run_id,
        output_dir=out_dir,
        diverted_from_root=diverted,
    )


def write_run_metadata(path: Path, metadata: Mapping[str, object]) -> None:
    path.write_text(json.dumps(dict(metadata), indent=2, default=str) + "\n", encoding="utf-8")
