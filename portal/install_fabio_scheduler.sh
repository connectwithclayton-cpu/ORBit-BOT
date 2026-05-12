#!/bin/bash
# install_fabio_scheduler.sh
# Run this ONCE to schedule orb_bot_fabio.py to auto-start at 9:25 AM on launchd weekdays.
# Actual starts are gated on the NYSE (XNYS) trading calendar via
# portal/run_fabio_if_nyse_trading_day.sh (skipped on exchange holidays).
# Regular-session market open timing comes from the calendar; typical open is 09:30 America/New_York.
#
# To uninstall: launchctl unload ~/Library/LaunchAgents/com.claytonorb.fabio.plist
#               rm ~/Library/LaunchAgents/com.claytonorb.fabio.plist

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FABIO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHONPATH_VAL="${FABIO_ROOT}/backend:${FABIO_ROOT}/frontend"

PLIST="$HOME/Library/LaunchAgents/com.claytonorb.fabio.plist"
LAUNCH_WRAP="$FABIO_ROOT/portal/run_fabio_if_nyse_trading_day.sh"
LOG="$FABIO_ROOT/orb_bot_fabio.log"
WORKDIR="$FABIO_ROOT"

# Resolve python3 path
PYTHON=$(which python3)
if [ -z "$PYTHON" ]; then
    echo "❌ python3 not found in PATH. Edit PYTHON= in this script to use the full path."
    exit 1
fi

cat > "$PLIST" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.claytonorb.fabio</string>

  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$LAUNCH_WRAP</string>
  </array>

  <key>WorkingDirectory</key>
  <string>$WORKDIR</string>

  <key>EnvironmentVariables</key>
  <dict>
    <key>PYTHONPATH</key>
    <string>$PYTHONPATH_VAL</string>
  </dict>

  <!-- 9:25 America/New_York weekdays (gate skips NYSE closed days—see EXCHANGE_CALENDAR.md) -->
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>25</integer></dict>
    <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>25</integer></dict>
    <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>25</integer></dict>
    <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>25</integer></dict>
    <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>25</integer></dict>
  </array>

  <key>RunAtLoad</key>
  <false/>

  <!-- Prevent launchd from restarting the bot if it crashes -->
  <key>KeepAlive</key>
  <false/>

  <key>StandardOutPath</key>
  <string>$LOG</string>
  <key>StandardErrorPath</key>
  <string>$LOG</string>
</dict>
</plist>
EOF

chmod +x "$LAUNCH_WRAP" 2>/dev/null || true

# Unload any previous version first
launchctl unload "$PLIST" 2>/dev/null

# Load the new plist
launchctl load "$PLIST"

if [ $? -eq 0 ]; then
    echo "✅ Fabio bot scheduler installed."
    echo "   Weekday trigger: 9:25 America/New_York (NYSE calendar gate)"
    echo "   Bot dir:   $WORKDIR"
    echo "   Log:       $LOG"
    echo ""
    echo "Useful commands:"
    echo "  Watch log live:  tail -f $LOG"
    echo "  Start now:       launchctl start com.claytonorb.fabio"
    echo "  Stop bot:        pkill -f orb_bot_fabio.py"
    echo "  Uninstall:       launchctl unload $PLIST && rm $PLIST"
else
    echo "❌ Failed to load plist. Check $PLIST for errors."
fi
