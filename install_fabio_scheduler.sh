#!/bin/bash
# install_fabio_scheduler.sh
# Run this ONCE to schedule orb_bot_fabio.py to auto-start at 9:25 AM ET Mon–Fri.
# The bot waits internally for 9:30 market open, so 9:25 gives it time to connect.
#
# To uninstall: launchctl unload ~/Library/LaunchAgents/com.claytonorb.fabio.plist
#               rm ~/Library/LaunchAgents/com.claytonorb.fabio.plist

PLIST="$HOME/Library/LaunchAgents/com.claytonorb.fabio.plist"
BOT="$HOME/Documents/TRADING/Fabio_bot/orb_bot_fabio.py"
LOG="$HOME/Documents/TRADING/Fabio_bot/orb_bot_fabio.log"
WORKDIR="$HOME/Documents/TRADING/Fabio_bot"

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
    <string>$PYTHON</string>
    <string>$BOT</string>
  </array>

  <key>WorkingDirectory</key>
  <string>$WORKDIR</string>

  <!-- 9:25 AM ET Mon–Fri (assumes Mac clock is set to ET) -->
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

# Unload any previous version first
launchctl unload "$PLIST" 2>/dev/null

# Load the new plist
launchctl load "$PLIST"

if [ $? -eq 0 ]; then
    echo "✅ Fabio bot scheduler installed."
    echo "   Starts at: 9:25 AM ET Mon–Fri"
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
