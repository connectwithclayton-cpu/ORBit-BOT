#!/usr/bin/env python3
"""Smoke-test Polygon Options REST access for Fabio comparison backtests.

Requires POLYGON_API_KEY (same key as equity bars) and a Polygon plan that
includes historical Options data. Exits 0 on success.

Usage (from Fabio_bot root, with PYTHONPATH):

    PYTHONPATH=backend:frontend python3 backend/tools/verify_polygon_options_access.py

Optional:

    PYTHONPATH=backend:frontend python3 backend/tools/verify_polygon_options_access.py --expiration-date 2024-05-03
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from fabio.settings import FabioBacktestSettings


def _friday_on_or_after(iso: str) -> str:
    d = date.fromisoformat(iso)
    while d.weekday() != 4:
        d += timedelta(days=1)
    return d.isoformat()


def _friday_on_or_before(iso: str) -> str:
    d = date.fromisoformat(iso)
    while d.weekday() != 4:
        d -= timedelta(days=1)
    return d.isoformat()


def _get(url: str, params: dict[str, Any], api_key: str) -> dict[str, Any]:
    import requests

    q = dict(params)
    q["apiKey"] = api_key
    r = requests.get(url, params=q, timeout=60)
    if r.status_code == 401:
        raise SystemExit("Polygon returned 401 — check POLYGON_API_KEY.")
    if r.status_code == 403:
        raise SystemExit(
            "Polygon returned 403 — key may lack Options coverage for this endpoint."
        )
    r.raise_for_status()
    return r.json()


def _first_contract(
    base: str, api_key: str, underlying: str, expiration_date: str
) -> dict[str, Any]:
    url = f"{base}/v3/reference/options/contracts"
    data = _get(
        url,
        {
            "underlying_ticker": underlying,
            "expiration_date": expiration_date,
            "contract_type": "call",
            "expired": "true",
            "limit": 50,
            "sort": "strike_price",
            "order": "asc",
        },
        api_key,
    )
    results = data.get("results") or []
    if not results:
        raise RuntimeError(
            f"No option contracts returned for {underlying} exp={expiration_date}. "
            "Pick an NYSE session date with listed weekly/monthly expiries."
        )
    mid = results[len(results) // 2]
    return mid


def _quotes_sample(base: str, api_key: str, options_ticker: str, day: str) -> int:
    url = f"{base}/v3/quotes/{options_ticker}"
    data = _get(
        url,
        {
            "timestamp.gte": day,
            "timestamp.lte": day,
            "limit": 50,
            "sort": "timestamp",
            "order": "asc",
        },
        api_key,
    )
    return len(data.get("results") or [])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--expiration-date",
        default="2024-05-03",
        help="Option expiration calendar date (YYYY-MM-DD), usually a listed Friday.",
    )
    parser.add_argument(
        "--range-start",
        default="2023-05-03",
        help="Session calendar date at start of Fabio backtest window.",
    )
    parser.add_argument(
        "--range-end",
        default="2026-05-03",
        help="Session calendar date at end of Fabio backtest window.",
    )
    args = parser.parse_args()

    cfg = FabioBacktestSettings.from_env()
    key = (cfg.polygon_api_key or "").strip()
    if len(key) < 10:
        raise SystemExit(
            "POLYGON_API_KEY is missing or too short. Set it in the environment or "
            "Fabio_bot/.env (see portal/.env.example)."
        )

    base = "https://api.polygon.io"
    symbols = cfg.symbols
    print(f"Checking Polygon Options for {', '.join(symbols)}…")

    exp = args.expiration_date
    for sym in symbols:
        c = _first_contract(base, key, sym, exp)
        ot = c.get("ticker")
        if not ot:
            raise RuntimeError(f"Contract payload missing ticker: {c!r}")
        n = _quotes_sample(base, key, ot, exp)
        print(f"  [{sym}] {ot} — {n} quote rows on {exp}")

    # Light coverage: SPY contracts expiring on boundary Fridays, quotes on boundary sessions.
    spy = symbols[0]
    boundaries = (
        ("range_start", args.range_start, _friday_on_or_after(args.range_start)),
        ("range_end", args.range_end, _friday_on_or_before(args.range_end)),
    )
    for label, session_day, expiry_day in boundaries:
        c = _first_contract(base, key, spy, expiry_day)
        ot = c.get("ticker")
        if not ot:
            raise RuntimeError(f"Contract payload missing ticker: {c!r}")
        n = _quotes_sample(base, key, ot, session_day)
        print(f"  [sanity:{label}] {ot} session={session_day} exp={expiry_day} — {n} quotes")
        if n == 0:
            print(
                "    Warning: no quotes — check Options history entitlement or pick another expiry.",
                file=sys.stderr,
            )

    print("Polygon Options probe completed successfully.")


if __name__ == "__main__":
    main()
