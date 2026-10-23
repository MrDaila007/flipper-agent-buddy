#!/bin/bash
set -euo pipefail

# beforeSubmitPrompt hook: show "Thinking..." on Flipper.

SOCKET="/tmp/cursor-flipper-bridge.sock"
PLUGIN_ROOT="${PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
export PLUGIN_ROOT

if [ ! -S "$SOCKET" ]; then
    printf '{"continue":true}\n'
    exit 0
fi

# Refresh the active input target from the session that just submitted a prompt.
python3 "${PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.}}/scripts/session-target.py" register_target "$SOCKET" >/dev/null 2>&1 || true

PAYLOAD=$(cat)
if [ -n "$PAYLOAD" ]; then
    echo "$PAYLOAD" | python3 "${PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.}}/scripts/context_usage.py" sync >/dev/null 2>&1 || true
fi

echo '{"action":"display","text":"Thinking...","subtext":""}' \
    | nc -U "$SOCKET" 2>/dev/null &

printf '{"continue":true}\n'
exit 0
