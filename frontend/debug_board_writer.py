"""
debug_board_writer.py — Generate Fabio_debug_board.html with config snapshot,
artifact file status, and optional log tail (no secrets in full).

Usage:
    python debug_board_writer.py

Outputs:
    Fabio_bot/frontend/Fabio_debug_board.html  (repo-local)
    ~/Documents/TRADING/Fabio_debug_board.html  (convenience copy)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_FABIO_ROOT = Path(__file__).resolve().parent.parent
_BACKEND = _FABIO_ROOT / "backend"
_TRADING = Path.home() / "Documents" / "TRADING"
_OUT_LOCAL = _FABIO_ROOT / "frontend" / "Fabio_debug_board.html"
_OUT_MAIN = _TRADING / "Fabio_debug_board.html"

_ARTIFACTS = [
    "Fabio_backtest_trades.csv",
    "Fabio_backtest_equity.csv",
    "Fabio_backtest_report.png",
    "Fabio_live_mirror_trades.csv",
    "Fabio_live_mirror_equity.csv",
    "Fabio_live_mirror_report.png",
    "backend/trade_data.json",
    "orb_bot_fabio.log",
    "dashboard_push.log",
]


def _mask_secret(val: str, keep: int = 4) -> str:
    if not val:
        return "(not set)"
    if len(val) <= keep:
        return "***"
    return "***" + val[-keep:]


def _git_rev() -> str:
    try:
        r = subprocess.run(
            ["git", "-C", str(_FABIO_ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return "n/a"


def _collect_payload() -> dict:
    bp = str(_BACKEND)
    if bp not in sys.path:
        sys.path.insert(0, bp)
    try:
        from backtest.fabio.settings import FabioBacktestSettings

        cfg = FabioBacktestSettings.from_env()
    except Exception as e:
        cfg = None
        cfg_err = str(e)
    else:
        cfg_err = None

    data_source = os.environ.get("FABIO_DATA_SOURCE", "").strip()
    try:
        import backtest.Fabio_orb_backtest as fb

        ds = getattr(fb, "DATA_SOURCE", None)
        if ds and not data_source:
            data_source = ds
    except Exception:
        pass

    env_snapshot = {
        "POLYGON_API_KEY": _mask_secret(os.environ.get("POLYGON_API_KEY", "")),
        "MOOMOO_TRADE_ENV": os.environ.get("MOOMOO_TRADE_ENV", "(not set)"),
        "MOOMOO_HOST": os.environ.get("MOOMOO_HOST", "(not set)"),
        "FABIO_DATA_SOURCE": data_source or "(not set)",
        "PYTHON": sys.version.split()[0],
        "cwd_hint": str(_FABIO_ROOT),
    }

    config_block = {}
    if cfg is not None:
        config_block = {
            "symbols": list(cfg.symbols),
            "start_date": cfg.start_date,
            "end_date": cfg.end_date,
            "initial_capital": cfg.initial_capital,
            "strategy_capital_cap": cfg.strategy_capital_cap,
            "data_source_resolved": cfg.data_source,
            "vix_skip": cfg.vix_skip,
            "vix_normal_max": cfg.vix_normal_max,
            "risk_pct_max": cfg.risk_pct_max,
        }
        try:
            import backtest.Fabio_orb_backtest as fb

            config_block["Fabio_orb_backtest.DATA_SOURCE"] = getattr(fb, "DATA_SOURCE", "")
        except Exception:
            pass

    files_out = []
    for name in _ARTIFACTS:
        p = _FABIO_ROOT / name  # name may include "backend/..." for nested artifacts
        try:
            st = p.stat()
            files_out.append(
                {
                    "name": name,
                    "path": str(p),
                    "exists": True,
                    "bytes": st.st_size,
                    "mtime_iso": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).strftime(
                        "%Y-%m-%d %H:%M UTC"
                    ),
                }
            )
        except FileNotFoundError:
            files_out.append({"name": name, "path": str(p), "exists": False})

    log_tail: list[str] = []
    log_path = _FABIO_ROOT / "orb_bot_fabio.log"
    if log_path.exists():
        try:
            raw = log_path.read_text(errors="replace").splitlines()
            log_tail = raw[-40:]
        except Exception as e:
            log_tail = [f"(read error: {e})"]

    beta_payload = None
    try:
        from fabio_beta_identity import beta_identity_payload

        beta_payload = beta_identity_payload()
    except ImportError:
        pass

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "git_rev": _git_rev(),
        "beta_identity": beta_payload,
        "config_error": cfg_err,
        "env": env_snapshot,
        "fabio_settings": config_block,
        "artifacts": files_out,
        "log_tail": log_tail,
        "cli": {
            "research_backtest": "PYTHONPATH=backend:frontend python3 backend/backtest/Fabio_orb_backtest.py",
            "live_mirror_backtest": "PYTHONPATH=backend:frontend python3 backend/backtest/Fabio_live_mirror_backtest.py",
            "verify_trades": "python3 backend/verify_trades.py",
            "force_close": "python3 backend/force_close.py",
        },
    }


_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Fabio — Debug Board</title>
<style>
:root {
  --bg: #0d0d0d;
  --surface: #161616;
  --border: #252525;
  --text: #e8e8e8;
  --muted: #777;
  --green: #00e676;
  --red: #ff5252;
  --blue: #4fc3f7;
  --yellow: #ffd740;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: var(--bg); color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  font-size: 13px;
  line-height: 1.45;
  padding-bottom: 48px;
}
header {
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  padding: 18px 28px;
  display: flex;
  align-items: baseline;
  gap: 16px;
  flex-wrap: wrap;
}
h1 { font-size: 18px; font-weight: 700; }
.meta { color: var(--muted); font-size: 12px; }
.badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.5px;
  border: 1px solid var(--border);
  color: var(--yellow);
}
.page { max-width: 1100px; margin: 0 auto; padding: 24px 28px; }
section { margin-bottom: 28px; }
h2 {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.6px;
  color: var(--muted);
  margin-bottom: 10px;
}
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px 16px;
}
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--border); }
th { color: var(--muted); font-weight: 600; font-size: 10px; text-transform: uppercase; letter-spacing: 0.4px; }
tr:last-child td { border-bottom: none; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; }
.err { color: var(--red); }
.ok { color: var(--green); }
pre.log {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 320px;
  overflow-y: auto;
  color: var(--muted);
}
dl.grid {
  display: grid;
  grid-template-columns: 160px 1fr;
  gap: 6px 12px;
}
dt { color: var(--muted); }
dd.mono { word-break: break-all; }
ul.cli { list-style: none; }
ul.cli li { margin-bottom: 6px; }
ul.cli code {
  background: var(--bg);
  padding: 2px 6px;
  border-radius: 4px;
  border: 1px solid var(--border);
}
</style>
</head>
<body>
<header>
  <h1>Fabio debug board</h1>
  <span class="badge" id="betaBadge" title="Beta — see beta_manifest.json">BETA</span>
  <span class="meta" id="hdr-meta"></span>
</header>
<div class="page">
  <section id="sec-err" style="display:none;">
    <h2>Config load</h2>
    <div class="card err mono" id="cfg-err"></div>
  </section>

  <section>
    <h2>Environment</h2>
    <div class="card"><dl class="grid" id="env-dl"></dl></div>
  </section>

  <section>
    <h2>Fabio settings snapshot</h2>
    <div class="card"><dl class="grid" id="cfg-dl"></dl></div>
  </section>

  <section>
    <h2>Artifacts</h2>
    <div class="card">
      <table id="art-table">
        <thead><tr><th>File</th><th>Status</th><th>Size</th><th>Modified</th></tr></thead>
        <tbody></tbody>
      </table>
    </div>
  </section>

  <section>
    <h2>CLI shortcuts</h2>
    <div class="card"><ul class="cli mono" id="cli-ul"></ul></div>
  </section>

  <section>
    <h2>orb_bot_fabio.log (tail)</h2>
    <div class="card"><pre class="log" id="log-pre"></pre></div>
  </section>
</div>
<script type="application/json" id="fabio-debug-json">__DEBUG_JSON_RAW__</script>
<script>
const DATA = JSON.parse(document.getElementById('fabio-debug-json').textContent);

(function () {
  (function () {
    const badge = document.getElementById('betaBadge');
    if (badge) badge.textContent = 'BETA';
  })();
  document.getElementById('hdr-meta').textContent =
    'Generated ' + DATA.generated_at + ' · git ' + DATA.git_rev;

  if (DATA.config_error) {
    document.getElementById('sec-err').style.display = 'block';
    document.getElementById('cfg-err').textContent = DATA.config_error;
  }

  const envDl = document.getElementById('env-dl');
  for (const [k, v] of Object.entries(DATA.env || {})) {
    const dt = document.createElement('dt'); dt.textContent = k;
    const dd = document.createElement('dd'); dd.className = 'mono'; dd.textContent = v;
    envDl.appendChild(dt); envDl.appendChild(dd);
  }

  const cfgDl = document.getElementById('cfg-dl');
  const fs = DATA.fabio_settings || {};
  if (Object.keys(fs).length === 0) {
    cfgDl.innerHTML = '<dt></dt><dd class="muted">(no fabio settings)</dd>';
  } else {
    for (const [k, v] of Object.entries(fs)) {
      const dt = document.createElement('dt'); dt.textContent = k;
      const dd = document.createElement('dd'); dd.className = 'mono';
      dd.textContent = typeof v === 'object' ? JSON.stringify(v) : String(v);
      cfgDl.appendChild(dt); cfgDl.appendChild(dd);
    }
  }

  const tb = document.querySelector('#art-table tbody');
  for (const row of DATA.artifacts || []) {
    const tr = document.createElement('tr');
    const ok = row.exists;
    tr.innerHTML =
      '<td class="mono">' + row.name + '</td>' +
      '<td class="' + (ok ? 'ok' : 'err') + '">' + (ok ? 'OK' : 'missing') + '</td>' +
      '<td class="mono">' + (ok ? row.bytes : '-') + '</td>' +
      '<td class="mono">' + (ok ? row.mtime_iso : '-') + '</td>';
    tb.appendChild(tr);
  }

  const cli = document.getElementById('cli-ul');
  for (const [label, cmd] of Object.entries(DATA.cli || {})) {
    const li = document.createElement('li');
    li.innerHTML = '<strong>' + label + '</strong> — <code>' + cmd + '</code>';
    cli.appendChild(li);
  }

  document.getElementById('log-pre').textContent =
    (DATA.log_tail || []).join(String.fromCharCode(10)) || '(no log lines)';
})();
</script>
</body>
</html>
"""


def write_debug_board() -> Path:
    payload = _collect_payload()
    data_json = json.dumps(payload, indent=2)
    # Safe embedding inside HTML (avoid closing </script> via log lines)
    data_safe = data_json.replace("<", "\\u003c")
    html = _TEMPLATE.replace("__DEBUG_JSON_RAW__", data_safe)

    for path in (_OUT_LOCAL, _OUT_MAIN):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(html)
        except Exception as e:
            print(f"[DebugBoard] Write failed ({path}): {e}")

    print(f"[DebugBoard] OK → {_OUT_MAIN}")
    return _OUT_LOCAL


if __name__ == "__main__":
    write_debug_board()
