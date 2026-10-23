#!/bin/bash
set -euo pipefail

# stop hook: notify Flipper when Cursor finishes a turn.

SOCKET="/tmp/cursor-flipper-bridge.sock"
STATS="/tmp/cursor-flipper-turn-stats.json"
SKIP_FLAG="/tmp/cursor-flipper-skip-stop.flag"

if [ ! -S "$SOCKET" ]; then
    rm -f "$STATS"
    exit 0
fi

if [ -f "$SKIP_FLAG" ]; then
    rm -f "$SKIP_FLAG" "$STATS"
    exit 0
fi

PAYLOAD=$(cat)

STATUS=$(echo "$PAYLOAD" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    print(data.get('status', 'completed'))
except Exception:
    print('completed')
" 2>/dev/null)

SUBTEXT=""
if [ -f "$STATS" ]; then
    SUBTEXT=$(python3 -c "
import json
try:
    stats = json.load(open('$STATS'))
    parts = sorted(stats.items(), key=lambda x: -x[1])
    summary = ' '.join(f'{v} {k}' for k, v in parts)
    print(summary[:21] if summary else '')
except Exception:
    print('')
" 2>/dev/null)
    rm -f "$STATS"
fi

case "$STATUS" in
    aborted|error)
        echo "{\"action\":\"notify\",\"sound\":\"interrupt\",\"vibro\":true,\"text\":\"Interrupted\",\"subtext\":\"$SUBTEXT\"}" \
            | nc -U "$SOCKET" 2>/dev/null &
        ;;
    *)
        echo "{\"action\":\"notify\",\"sound\":\"success\",\"vibro\":true,\"text\":\"Turn complete\",\"subtext\":\"$SUBTEXT\"}" \
            | nc -U "$SOCKET" 2>/dev/null &
        ;;
esac

exit 0
