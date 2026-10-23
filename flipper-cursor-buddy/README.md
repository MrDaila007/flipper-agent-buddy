# Flipper Cursor Buddy

Cursor CLI hooks that connect agent lifecycle events to the Flipper Zero buddy
application over USB or Bluetooth.

## Features

- Session, turn, compaction, and subagent status on Flipper Zero
- Per-tool sounds and compact per-turn statistics
- Allow or deny tool use from Flipper Zero (`preToolUse`)
- Command menu input through the active Cursor terminal
- USB and BLE transports using the host bridge

## Install

From the repository root:

```sh
chmod +x flipper-cursor-buddy/scripts/install-cursor-hooks.sh
./flipper-cursor-buddy/scripts/install-cursor-hooks.sh
```

This merges hook definitions into `.cursor/hooks.json`. Open **Settings → Hooks**
in Cursor and confirm the hooks are loaded, then start a new agent session.

## Requirements

- Cursor with project hooks support
- Python 3.10 or newer
- Flipper Zero running the buddy application
- `nc` and the platform-specific input dependencies used by the host bridge

## Configuration

```sh
export FLIPPER_TRANSPORT=auto     # auto, usb, or ble
export FLIPPER_SERIAL_PORT=       # optional explicit USB serial port
export FLIPPER_BT_NAME=Flipper    # optional BLE name fallback
export FLIPPER_HOST_TYPE=cursor   # sent to Flipper in state messages (default: cursor)
```

The Flipper status header shows **Cursor** when this bridge is connected.

The plugin stores its virtual environment and detected Bluetooth name under
`PLUGIN_DATA` (default `/tmp/flipper-cursor-buddy`). Its runtime socket is
`/tmp/cursor-flipper-bridge.sock`. Bridge enablement is persisted in
`PLUGIN_DATA/bridge-enabled` and can be changed with:

```sh
flipper-cursor-buddy/bin/flipper-bridge enable|disable|status
```

## Cursor hooks

| Cursor event | Flipper behavior |
|---|---|
| `sessionStart` | Start bridge, connect notification |
| `sessionEnd` | Disconnect notification |
| `beforeSubmitPrompt` | "Thinking..." display |
| `preToolUse` | Permission prompt on Flipper |
| `postToolUse` | Per-tool sound + context meters |
| `postToolUseFailure` | Error sound |
| `preCompact` | Compacting animation + context pressure |
| `subagentStart` / `subagentStop` | Subagent status |
| `stop` | Turn complete summary |

Cursor does not expose `postCompact`; compaction completion is signaled on the
first `postToolUse` after compaction via an internal flag.

## Custom commands

Optional shortcut files (project overrides user):

1. `~/.cursor/flipper-commands.txt`
2. `$PROJECT_DIR/.cursor/flipper-commands.txt`
