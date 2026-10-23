#!/bin/bash
set -euo pipefail

# sessionEnd hook: disconnect Flipper and stop bridge when last session ends.

SOCKET="/tmp/cursor-flipper-bridge.sock"
PIDFILE="/tmp/cursor-flipper-bridge.pid"
REFCOUNT_FILE="/tmp/cursor-flipper-bridge.refcount"

PLUGIN_ROOT="${PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

PAYLOAD=$(cat)
REASON=$(echo "$PAYLOAD" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
    raw = data.get("reason") or data.get("final_status") or ""
    print(str(raw)[:21] if raw else "Disconnected")
except Exception:
    print("Disconnected")
' 2>/dev/null)

COUNT=$(cat "$REFCOUNT_FILE" 2>/dev/null || echo 1)
COUNT=$((COUNT - 1))
if [ "$COUNT" -lt 0 ]; then COUNT=0; fi
echo "$COUNT" > "$REFCOUNT_FILE"

if [ -S "$SOCKET" ]; then
    python3 "$PLUGIN_ROOT/scripts/session-target.py" release_target "$SOCKET" >/dev/null 2>&1 || true
    echo '{"action":"cursor_disconnect"}' | nc -U "$SOCKET" 2>/dev/null || true
fi

if [ "$COUNT" -le 0 ]; then
    if [ -S "$SOCKET" ]; then
        echo "{\"action\":\"notify\",\"sound\":\"session_end\",\"vibro\":true,\"text\":\"Session End\",\"subtext\":\"$REASON\"}" \
            | nc -U "$SOCKET" 2>/dev/null || true
        sleep 0.5
    fi

    if [ -f "$PIDFILE" ]; then
        PID=$(cat "$PIDFILE")
        if kill -0 "$PID" 2>/dev/null; then
            kill "$PID"
        fi
        rm -f "$PIDFILE"
    fi
    rm -f "$REFCOUNT_FILE"
fi

exit 0
