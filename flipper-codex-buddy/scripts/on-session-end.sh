#!/usr/bin/env bash
# SessionEnd has a three-second maximum. The daemon owns session accounting
# and shuts down only after the last thread ends.
set -euo pipefail
PLUGIN_ROOT="${PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
exec python3 "$PLUGIN_ROOT/scripts/session-target.py" end_session \
    "${FLIPPER_BRIDGE_SOCKET:-/tmp/codex-flipper-bridge.sock}"
