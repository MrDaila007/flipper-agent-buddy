#!/bin/bash
set -euo pipefail

# UserPromptSubmit hook: show "Thinking..." on Flipper when user sends a prompt

SOCKET="/tmp/codex-flipper-bridge.sock"

if [ ! -S "$SOCKET" ]; then
    exit 0
fi

PAYLOAD=$(cat)

# Refresh the active input target from the session that just submitted a prompt.
printf '%s' "$PAYLOAD" | python3 "${PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.}}/scripts/session-target.py" register_target "$SOCKET" >/dev/null 2>&1 || true

if [ -n "$PAYLOAD" ]; then
    echo "$PAYLOAD" | python3 "${PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.}}/scripts/context_usage.py" sync >/dev/null 2>&1 || true
fi

echo '{"action":"display","text":"Thinking...","subtext":""}' \
    | nc -U "$SOCKET" 2>/dev/null &

exit 0
