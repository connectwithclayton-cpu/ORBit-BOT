from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_audit_module():
    root = Path(__file__).resolve().parents[1]
    mod_path = root / "scripts" / "audit_moomoo_sync.py"
    spec = importlib.util.spec_from_file_location("audit_moomoo_sync", mod_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_option_code_detection():
    mod = _load_audit_module()
    assert mod._is_option_code("US.SPY260507C00735000")
    assert mod._is_option_code("US.QQQ260507P00670000")
    assert not mod._is_option_code("US.SPY")


def test_normalize_broker_fill_rows_filters_non_option_and_non_sell():
    mod = _load_audit_module()
    rows = [
        [
            "fid1",
            "2026-05-07 10:00:00",
            "2026-05-07",
            "US.SPY260507C00735000",
            "SPY",
            "CALL",
            "SELL",
            "2",
            "1.25",
            "250",
            "40",
            "moomoo_paper",
        ],
        [
            "fid2",
            "2026-05-07 10:01:00",
            "2026-05-07",
            "US.SPY260507C00735000",
            "SPY",
            "CALL",
            "BUY",
            "2",
            "1.20",
            "240",
            "0",
            "moomoo_paper",
        ],
        [
            "fid3",
            "2026-05-07 10:02:00",
            "2026-05-07",
            "US.SPY",
            "SPY",
            "PUT",
            "SELL",
            "1",
            "1.00",
            "100",
            "0",
            "moomoo_paper",
        ],
    ]
    out = mod._normalize_broker_fill_rows(rows)
    assert len(out) == 1
    assert out[0]["fill_id"] == "fid1"


def test_severity_escalates_on_repeated_hard_failures():
    mod = _load_audit_module()
    s1 = mod._severity_from_failures(["missing_broker_fill_ids:1"], True, False, 1)
    assert s1.severity == "WARNING"
    s2 = mod._severity_from_failures(["missing_broker_fill_ids:1"], True, False, 2)
    assert s2.severity == "CRITICAL"
