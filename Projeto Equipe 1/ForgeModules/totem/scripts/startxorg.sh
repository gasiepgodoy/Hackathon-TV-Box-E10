#!/usr/bin/env bash

# Safety settings: exit on error, treat unset variables as an error
set -euo pipefail

DISPLAY_NUM=":0"
TIMEOUT_SECONDS=6

echo "=== Pre-Start Cleanup ==="

# 1. Kill any existing Xorg process specifically running on this display
# This targets the process command line rather than blindly killing all Xorg instances
EXISTING_X_PID=$(pgrep -f "Xorg.*$DISPLAY_NUM" || pgrep -f "xinit.*$DISPLAY_NUM" || true)
if [ -n "$EXISTING_X_PID" ]; then
    echo "Found previous Xorg instance running on $DISPLAY_NUM (PIDs: $EXISTING_X_PID). Terminating..."
    kill $EXISTING_X_PID 2>/dev/null || true
    sleep 1
    kill -9 $EXISTING_X_PID 2>/dev/null || true
fi

# 2. Clear stale lock and socket files for display :0
# Xorg won't start if these files exist, even if the old process is dead
DISPLAY_DIGIT="${DISPLAY_NUM#?:}" # Extracts '0' from ':0'
LOCK_FILE="/tmp/.X${DISPLAY_DIGIT}-lock"
SOCKET_FILE="/tmp/.X11-unix/X${DISPLAY_DIGIT}"

if [ -f "$LOCK_FILE" ] || [ -S "$SOCKET_FILE" ]; then
    echo "Cleaning up left-over lock/socket files for $DISPLAY_NUM..."
    rm -f "$LOCK_FILE" "$SOCKET_FILE"
fi

echo "========================="
echo "Attempting to start Xorg via startx on $DISPLAY_NUM safely..."

# 3. Start startx in the background. 
# We direct it to our specific display and pipe logs to a file.
startx -- "$DISPLAY_NUM" > /tmp/startx_safe.log 2>&1 &
STARTX_PID=$!

echo "startx launched with PID $STARTX_PID. Watching for locks..."

# 4. Watchdog loop to ensure it doesn't freeze the screen
for ((i=1; i<=TIMEOUT_SECONDS; i++)); do
    sleep 1
    
    # Check if startx died early on its own
    if ! kill -0 "$STARTX_PID" 2>/dev/null; then
        echo "startx exited unexpectedly. Check /tmp/startx_safe.log"
        break
    fi

    # Check if the display is up and running
    if DISPLAY="$DISPLAY_NUM" xset q >/dev/null 2>&1; then
        echo "Successfully connected to Xorg via startx on $DISPLAY_NUM!"
        exit 0
    fi
done

# 5. Emergency Recovery: If it hangs, kill the entire process tree
echo "startx timed out or hung. Forcing screen recovery..."

# Kill startx and any sub-processes (like Xorg itself) it spawned
PARENT_PID=$STARTX_PID
# Get child PIDs (Xorg is usually spawned by xinit, which startx calls)
CHILD_PIDS=$(pgrep -P "$PARENT_PID" 2>/dev/null || true)

for pid in $CHILD_PIDS $PARENT_PID; do
    kill "$pid" 2>/dev/null || true
done

sleep 1

# Hard kill if it refuses to die
for pid in $CHILD_PIDS $PARENT_PID; do
    kill -9 "$pid" 2>/dev/null || true
done

# 6. Debian-specific TTY un-jamming
# Debian uses systemd-logind. If the VT gets stuck, we force a switch back.
if command -v chvt &> /dev/null; then
    # Try to detect your active TTY, default to TTY 1 if it can't find it
    CURRENT_TTY=$(tty | grep -o '[0-9]\+$' || echo "1")
    echo "Switching back to TTY $CURRENT_TTY..."
    sudo chvt "$CURRENT_TTY" 2>/dev/null || chvt "$CURRENT_TTY" 2>/dev/null || true
fi

# Reset terminal behavior just in case keystrokes are invisible
stty sane 2>/dev/null || true

echo "Screen recovered. View details in /tmp/startx_safe.log"
exit 1
