#!/usr/bin/env bash
# Register the repo marketplace and install the Flipper Agent Buddy Codex adapter.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MARKETPLACE_NAME="flipper-local"
PLUGIN_NAME="flipper-agent-buddy-codex"

VALIDATOR="$HOME/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py"
if [ -f "$VALIDATOR" ]; then
  echo "Validating plugin manifest..."
  python3 "$VALIDATOR" "$REPO_ROOT/flipper-codex-buddy"
fi

echo "Registering marketplace at $REPO_ROOT..."
codex plugin marketplace add "$REPO_ROOT"

echo "Installing $PLUGIN_NAME@$MARKETPLACE_NAME..."
codex plugin add "$PLUGIN_NAME@$MARKETPLACE_NAME"

echo ""
echo "Installed. In Codex:"
echo "  1. Open /hooks and trust the Flipper Agent Buddy Codex adapter hooks"
echo "  2. Start a new thread so hooks and slash commands load"
echo "  3. Use /bridge-status to check the bridge"
