# Flipper Codex Buddy

Codex plugin that connects lifecycle hooks to the existing Flipper Zero buddy
application over USB or Bluetooth.

## Features

- Codex session, turn, compaction, and subagent status on Flipper Zero
- Tool-use sounds and compact per-turn statistics
- Allow or deny Codex permission requests from Flipper Zero
- Slash-command and skill menu input through the active Codex terminal
- USB and BLE transports using the existing host bridge

## Install

From the repository root:

```sh
./flipper-codex-buddy/scripts/install-codex-plugin.sh
```

This registers the local marketplace (`flipper-local`), installs
`flipper-codex-buddy`, and prints the post-install steps. After install, open
`/hooks` in Codex and trust the plugin hook definition, then start a new thread.

## Requirements

- Codex CLI with plugin and lifecycle-hook support
- Python 3.10 or newer
- Flipper Zero running the buddy application
- `nc` and the platform-specific input dependencies used by the host bridge

## Configuration

The bridge uses environment variables because Codex plugin manifests do not
provide Claude-style `userConfig` options:

```sh
export FLIPPER_TRANSPORT=auto     # auto, usb, or ble
export FLIPPER_SERIAL_PORT=       # optional explicit USB serial port
export FLIPPER_BT_NAME=Flipper    # optional BLE name fallback
export FLIPPER_HOST_TYPE=codex    # sent to Flipper in state messages (default: codex)
```

The Flipper status header shows **Codex** when this bridge is connected.

The plugin stores its virtual environment and detected Bluetooth name under
`PLUGIN_DATA`. Its runtime socket is `/tmp/codex-flipper-bridge.sock`.
Bridge enablement is persisted in `PLUGIN_DATA/bridge-enabled` and can be
changed with the Codex slash commands `/bridge`, `/bridge-on`, `/bridge-off`,
and `/bridge-status`.

## Codex hooks

After installation, open `/hooks` in Codex and trust the plugin hook definition.
The plugin handles `SessionStart` (including forked threads), `SessionEnd`,
`Interrupt`, `UserPromptSubmit`, `PermissionRequest`, `PostToolUse`, compaction,
subagent lifecycle, and `Stop`. Session tracking uses Codex thread IDs, so
resuming or compacting a thread does not create a duplicate bridge session.

Codex hooks currently support one-shot allow/deny decisions. The Flipper
"Always" choice is therefore treated as a one-shot allow in this plugin.
