#!/usr/bin/env bash
# SessionEnd has a three-second maximum. The daemon owns session accounting
# and shuts down only after the last thread ends.
set -euo pipefail
PLUGIN_ROOT="${PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
RUNTIME_DIR="${FLIPPER_RUNTIME_DIR:-${XDG_RUNTIME_DIR:+$XDG_RUNTIME_DIR/flipper-codex-buddy}}"
RUNTIME_DIR="${RUNTIME_DIR:-/tmp/flipper-codex-buddy-$(id -u)}"
exec python3 "$PLUGIN_ROOT/scripts/session-target.py" end_session \
    "${FLIPPER_BRIDGE_SOCKET:-$RUNTIME_DIR/bridge.sock}"
