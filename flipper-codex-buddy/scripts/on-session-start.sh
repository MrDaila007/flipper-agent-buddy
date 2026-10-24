#!/bin/bash
set -euo pipefail

# Codex SessionStart hook: ensure bridge is running, then notify Flipper.

RUNTIME_DIR="${FLIPPER_RUNTIME_DIR:-${XDG_RUNTIME_DIR:+$XDG_RUNTIME_DIR/flipper-codex-buddy}}"
RUNTIME_DIR="${RUNTIME_DIR:-/tmp/flipper-codex-buddy-$(id -u)}"
SOCKET="${FLIPPER_BRIDGE_SOCKET:-$RUNTIME_DIR/bridge.sock}"
PIDFILE="${FLIPPER_BRIDGE_PIDFILE:-$RUNTIME_DIR/bridge.pid}"
LOG="${FLIPPER_BRIDGE_LOG:-$RUNTIME_DIR/bridge.log}"
if [ -L "$RUNTIME_DIR" ] || { [ -e "$RUNTIME_DIR" ] && [ ! -O "$RUNTIME_DIR" ]; }; then
    echo "Flipper runtime directory must be an owned real directory: $RUNTIME_DIR" >&2
    exit 1
fi
mkdir -p -m 700 "$RUNTIME_DIR"
chmod 700 "$RUNTIME_DIR"

# Read hook payload from stdin and extract source for display subtext.
PAYLOAD=$(cat)
SUBTEXT=$(echo "$PAYLOAD" | python3 -c '
import json, sys
SOURCES = {
    "startup": "New session",
    "resume": "Resumed",
    "clear": "After clear",
    "compact": "After compaction",
}
try:
    data = json.load(sys.stdin)
    source = data.get("source") or ""
    label = SOURCES.get(source, "")
    if not label:
        label = (data.get("model") or "")[:21]
    print(label)
except Exception:
    print("")
' 2>/dev/null)

PLUGIN_ROOT="${PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.}}"
PLUGIN_DATA="${PLUGIN_DATA:-${CLAUDE_PLUGIN_DATA:-/tmp/flipper-codex-buddy}}"
BRIDGE_DIR="$PLUGIN_ROOT/host-bridge"
VENV_DIR="$PLUGIN_DATA/venv"
MARKER="$VENV_DIR/.installed-hash"
BRIDGE_STATE_FILE="${FLIPPER_BRIDGE_ENABLED_FILE:-$PLUGIN_DATA/bridge-enabled}"
CURRENT_HASH=$(cat "$BRIDGE_DIR/pyproject.toml" "$BRIDGE_DIR"/bridge/*.py 2>/dev/null | md5 -q 2>/dev/null || cat "$BRIDGE_DIR/pyproject.toml" "$BRIDGE_DIR"/bridge/*.py 2>/dev/null | md5sum | cut -d' ' -f1 || echo "none")

# Stop the prior shared-/tmp daemon once, so it releases BLE before migration.
LEGACY_SOCKET="/tmp/codex-flipper-bridge.sock"
if [ "$SOCKET" != "$LEGACY_SOCKET" ] && [ -S "$LEGACY_SOCKET" ]; then
    if python3 -c 'import os,socket,stat,sys; s=os.stat(sys.argv[1]); sys.exit(0 if stat.S_ISSOCK(s.st_mode) and s.st_uid == os.getuid() and not (s.st_mode & 0o077) else 1)' "$LEGACY_SOCKET" 2>/dev/null; then
        printf '{"action":"shutdown"}\n' | nc -U "$LEGACY_SOCKET" >/dev/null 2>&1 || true
        for _ in $(seq 1 30); do
            [ -S "$LEGACY_SOCKET" ] || break
            sleep 0.1
        done
    fi
fi

mkdir -p -m 700 "$RUNTIME_DIR"
chmod 700 "$RUNTIME_DIR"

# Codex plugin options are configured through FLIPPER_* environment variables.
# Fall back to the previously auto-detected Bluetooth name when unset.
BT_NAME_CACHE="$PLUGIN_DATA/bt_name"
if [ -z "${FLIPPER_BT_NAME:-}" ] && [ -f "$BT_NAME_CACHE" ]; then
    export FLIPPER_BT_NAME="$(cat "$BT_NAME_CACHE")"
fi

# Pass PLUGIN_DATA to bridge so it can write the BT name cache after hello
export FLIPPER_PLUGIN_DATA="$PLUGIN_DATA"

# Pass current project directory so the bridge can discover Codex skills.
export FLIPPER_PROJECT_DIR="$(pwd)"

# Skip if no Flipper is connected (unless bridge is already running)
if [ ! -S "$SOCKET" ]; then
    TRANSPORT="${FLIPPER_TRANSPORT:-auto}"
    if [ -n "${FLIPPER_SERIAL_PORT:-}" ]; then
        # Explicit USB port configured — check it exists
        if [ ! -e "$FLIPPER_SERIAL_PORT" ]; then
            exit 0
        fi
    elif [ "$TRANSPORT" = "usb" ]; then
        # USB-only mode — require a USB device (macOS: cu.usbmodem*, Linux: ttyACM*)
        if ! compgen -G '/dev/cu.usbmodem*' >/dev/null && ! compgen -G '/dev/ttyACM*' >/dev/null; then
            exit 0
        fi
    fi
    # "ble" or "auto" transport: always attempt — BLE cannot be pre-checked from shell
fi

BRIDGE_ENABLED="1"
if [ -f "$BRIDGE_STATE_FILE" ]; then
    BRIDGE_ENABLED=$(cat "$BRIDGE_STATE_FILE" 2>/dev/null || echo "1")
fi
case "$BRIDGE_ENABLED" in
    0|false|False|off|disabled)
        BRIDGE_ENABLED="0"
        ;;
    *)
        BRIDGE_ENABLED="1"
        ;;
esac

# Clean up stale socket/pid if the bridge process is dead
if [ -S "$SOCKET" ] && [ -f "$PIDFILE" ]; then
    OLD_PID=$(cat "$PIDFILE" 2>/dev/null || echo "")
    INSTALLED_HASH=$(cat "$MARKER" 2>/dev/null || echo "")
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null && [ "$INSTALLED_HASH" != "$CURRENT_HASH" ]; then
        echo "[bridge] Bridge code changed; restarting daemon $OLD_PID..." >&2
        kill "$OLD_PID" 2>/dev/null || true
        rm -f "$SOCKET" "$PIDFILE" "/tmp/codex-flipper-bridge.refcount"
        OLD_PID=""
    fi
    if [ -n "$OLD_PID" ] && ! kill -0 "$OLD_PID" 2>/dev/null; then
        echo "[bridge] Cleaning up stale bridge (pid $OLD_PID gone)..." >&2
        rm -f "$SOCKET" "$PIDFILE" "/tmp/codex-flipper-bridge.refcount"
    fi
elif [ -S "$SOCKET" ] && [ ! -f "$PIDFILE" ]; then
    # Socket exists but no pidfile — check if anything is listening
    if ! echo '{}' | nc -U "$SOCKET" -w 1 >/dev/null 2>&1; then
        echo "[bridge] Cleaning up orphaned socket..." >&2
        rm -f "$SOCKET"
    fi
fi

# Start bridge if not already running and enabled
if [ "$BRIDGE_ENABLED" = "0" ]; then
    if [ -S "$SOCKET" ] && [ -f "$PIDFILE" ]; then
        OLD_PID=$(cat "$PIDFILE" 2>/dev/null || echo "")
        if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
            echo "[bridge] Bridge disabled; stopping daemon $OLD_PID..." >&2
            kill "$OLD_PID" 2>/dev/null || true
        fi
        rm -f "$SOCKET" "$PIDFILE" "/tmp/codex-flipper-bridge.refcount"
    fi
    exit 0
fi

# Start bridge if not already running
if [ ! -S "$SOCKET" ]; then
    echo "[bridge] Starting flipper bridge..." >&2

    # Create venv if it doesn't exist or any source file changed
    if [ ! -d "$VENV_DIR" ] || [ ! -f "$MARKER" ] || [ "$(cat "$MARKER" 2>/dev/null)" != "$CURRENT_HASH" ]; then
        echo "[bridge] Setting up Python environment..." >&2
        mkdir -p "$PLUGIN_DATA"
        python3 -m venv "$VENV_DIR"
        "$VENV_DIR/bin/pip" install -q --force-reinstall "$BRIDGE_DIR" 2>&1 | tail -1 >&2
        echo "$CURRENT_HASH" > "$MARKER"
    fi

    nohup "$VENV_DIR/bin/python" -m bridge </dev/null >> "$LOG" 2>&1 &
    echo $! > "$PIDFILE"

    for i in $(seq 1 30); do
        [ -S "$SOCKET" ] && break
        sleep 0.1
    done
fi

if [ ! -S "$SOCKET" ]; then
    echo "[bridge] Socket not available, bridge may have failed. Check $LOG" >&2
    exit 0
fi

# Register the thread and input target together. Repeated starts after resume or
# compaction are idempotent; the daemon tracks distinct session ids.
printf '%s' "$PAYLOAD" | python3 "$PLUGIN_ROOT/scripts/session-target.py" connect_session "$SOCKET" >/dev/null 2>&1 || true

exit 0
