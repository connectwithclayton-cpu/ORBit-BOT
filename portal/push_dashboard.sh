#!/bin/bash
# push_dashboard.sh — Sync Fabio live dashboard to GitHub Pages.
# Runs automatically at 12:00 PM and 3:55 PM ET Mon–Fri via launchd.
# Can also be run manually: bash portal/push_dashboard.sh (from Fabio_bot root).
#
# Defaults publish into THIS repo (ORBit-BOT / Fabio root) so Pages at
#   https://connectwithclayton-cpu.github.io/ORBit-BOT/
# picks up frontend/live_dashboard.html. Override REPO_DIR to push elsewhere
# (legacy: ~/Documents/TRADING/orb-live-dashboard).

FABIO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIVE_SRC="${LIVE_SRC:-$FABIO_ROOT/frontend/live_dashboard.html}"
BACKTEST_SRC="${BACKTEST_SRC:-$HOME/Documents/TRADING/orb_vs_fabio_dashboard.html}"
REPO_DIR="${REPO_DIR:-$FABIO_ROOT}"
LIVE_REL="${LIVE_REL:-frontend/live_dashboard.html}"
BACKTEST_REL="${BACKTEST_REL:-orb_vs_fabio_dashboard.html}"
LOG="$FABIO_ROOT/dashboard_push.log"

echo "" >> "$LOG"
echo "=== Fabio Push: $(date) ===" >> "$LOG"

if [ ! -d "$REPO_DIR/.git" ]; then
    echo "❌ Repo not found at $REPO_DIR" >> "$LOG"
    exit 1
fi

cd "$REPO_DIR"

# ── Fabio live dashboard ──────────────────────────────────────────────────────
if [ -f "$LIVE_SRC" ]; then
    mkdir -p "$(dirname "$REPO_DIR/$LIVE_REL")"
    cp "$LIVE_SRC" "$REPO_DIR/$LIVE_REL"
    git add "$LIVE_REL"
    echo "  staged $LIVE_REL" >> "$LOG"
else
    echo "⚠  Fabio dashboard not found at $LIVE_SRC — skipping." >> "$LOG"
fi

# ── Backtest comparison dashboard (optional) ─────────────────────────────────
if [ -f "$BACKTEST_SRC" ]; then
    cp "$BACKTEST_SRC" "$REPO_DIR/$BACKTEST_REL"
    git add "$BACKTEST_REL"
    echo "  staged $BACKTEST_REL" >> "$LOG"
else
    echo "⚠  Backtest dashboard not found at $BACKTEST_SRC — skipping." >> "$LOG"
fi

if git diff --cached --quiet; then
    echo "✓  No changes since last push — skipping." >> "$LOG"
    exit 0
fi

if git commit -m "Fabio dashboard update: $(date '+%Y-%m-%d %H:%M ET')" >> "$LOG" 2>&1; then
    :
else
    echo "❌ Commit failed — see $LOG" >> "$LOG"
    exit 1
fi

if git push origin main >> "$LOG" 2>&1; then
    echo "✅ Pushed successfully at $(date '+%H:%M')" >> "$LOG"
else
    echo "❌ Push failed — check auth / network." >> "$LOG"
    exit 1
fi
