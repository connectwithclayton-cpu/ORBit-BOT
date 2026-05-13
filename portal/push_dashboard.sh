#!/bin/bash
# push_dashboard.sh — Sync Fabio live dashboard to GitHub Pages.
# Runs automatically at 12:00 PM and 3:55 PM ET Mon–Fri via launchd.
# Can also be run manually: bash portal/push_dashboard.sh (from Fabio_bot root).
# Default LIVE_SRC: tracked snapshot at frontend/live_dashboard.html (override with env).

FABIO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIVE_SRC="${LIVE_SRC:-$FABIO_ROOT/frontend/live_dashboard.html}"
BACKTEST_SRC="${BACKTEST_SRC:-$HOME/Documents/TRADING/orb_vs_fabio_dashboard.html}"
REPO_DIR="${REPO_DIR:-$HOME/Documents/TRADING/orb-live-dashboard}"
LOG="$FABIO_ROOT/dashboard_push.log"

echo "" >> "$LOG"
echo "=== Fabio Push: $(date) ===" >> "$LOG"

# ── Guard: repo must be initialised ──────────────────────────────────────────
if [ ! -d "$REPO_DIR/.git" ]; then
    echo "❌ Repo not found at $REPO_DIR" >> "$LOG"
    exit 1
fi

cd "$REPO_DIR"
CHANGED=0

# ── Fabio live dashboard ──────────────────────────────────────────────────────
if [ -f "$LIVE_SRC" ]; then
    cp "$LIVE_SRC" "$REPO_DIR/fabio_live_dashboard.html"
    if ! git diff --quiet HEAD -- fabio_live_dashboard.html 2>/dev/null || \
       git ls-files --others --exclude-standard | grep -q "fabio_live_dashboard.html"; then
        git add fabio_live_dashboard.html
        CHANGED=1
        echo "  + fabio_live_dashboard.html updated" >> "$LOG"
    fi
else
    echo "⚠  Fabio dashboard not found at $LIVE_SRC — skipping." >> "$LOG"
fi

# ── Backtest comparison dashboard ─────────────────────────────────────────────
if [ -f "$BACKTEST_SRC" ]; then
    cp "$BACKTEST_SRC" "$REPO_DIR/orb_vs_fabio_dashboard.html"
    if ! git diff --quiet HEAD -- orb_vs_fabio_dashboard.html 2>/dev/null || \
       git ls-files --others --exclude-standard | grep -q "orb_vs_fabio_dashboard.html"; then
        git add orb_vs_fabio_dashboard.html
        CHANGED=1
        echo "  + orb_vs_fabio_dashboard.html updated" >> "$LOG"
    fi
else
    echo "⚠  Backtest dashboard not found at $BACKTEST_SRC — skipping." >> "$LOG"
fi

# ── Commit and push if anything changed ──────────────────────────────────────
if [ "$CHANGED" -eq 0 ]; then
    echo "✓  No changes since last push — skipping." >> "$LOG"
    exit 0
fi

git commit -m "Fabio dashboard update: $(date '+%Y-%m-%d %H:%M ET')" >> "$LOG" 2>&1
git push origin main >> "$LOG" 2>&1

if [ $? -eq 0 ]; then
    echo "✅ Pushed successfully at $(date '+%H:%M')" >> "$LOG"
else
    echo "❌ Push failed — check SSH key / network." >> "$LOG"
fi
