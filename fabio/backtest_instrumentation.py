"""
Optional NDJSON timing / diagnostics for backtest CLI scripts.

Set env ``FABIO_BACKTEST_DEBUG_LOG`` to a writable file path (e.g.
``./fabio_backtest_debug.ndjson``). If unset or empty, logging is a no-op.
"""

from __future__ import annotations

import json
import os
import time


def log_backtest_debug(
    hypothesis_id: str,
    location: str,
    message: str,
    data: dict,
    *,
    run_id: str = "backtest",
) -> None:
    path = os.environ.get("FABIO_BACKTEST_DEBUG_LOG", "").strip()
    if not path:
        return
    try:
        payload = {
            "runId": run_id,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, default=str) + "\n")
    except Exception:
        pass
