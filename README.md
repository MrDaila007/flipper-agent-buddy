# Flipper Agent Buddy

Turn your Flipper Zero into a universal physical companion for coding agents. One device app connects agent-specific adapters to a common status display, attention queue, and button interface. A shared host core is the target architecture; bridge consolidation is underway.

Initial adapters support **Claude Code**, **OpenAI Codex**, and **Cursor**. **Claude Desktop** connects directly over BLE through Anthropic's Hardware Buddy protocol. Additional agents can be added through adapters without changing the Flipper UI.

This repository is independently maintained. It retains the MIT license notice
for code derived from Flipper Claude Buddy; see [NOTICE](NOTICE) and [LICENSE](LICENSE).
The universal host-core and adapter architecture is developed here. See
[the architecture](docs/ARCHITECTURE.md).

> Supports macOS and Linux. Windows is not tested.

## What it does

**You feel what the agent is doing.**
Every significant event triggers a distinct sound and vibration pattern on your Flipper, so you always know status even when you are not looking at the screen.

**You see which agent is active.**
The status header shows the connected agent's name in the top-left corner.

**You respond to agent requests with physical buttons.**
Approval prompts and supported choice questions can be handled from the Flipper. Some general controls still forward key presses to the active terminal; native, agent-independent controls are being added through adapter capabilities.

**The character reacts to each tool.**
Reading, editing, terminal commands, searches, and delegated work each get their own animated pose. Compaction, permission outcomes, and context pressure also change the character and optional Ctx/Lim meters.

## Supported agents

| Agent | Package | Install doc | IPC socket |
|-------|---------|-------------|------------|
| **Claude Code** | `plugin/` | [Setup below](#claude-code) | `/tmp/claude-flipper-bridge.sock` |
| **OpenAI Codex adapter** | `flipper-codex-buddy/` | [Codex adapter README](flipper-codex-buddy/README.md) | local IPC |
| **Cursor adapter** | `flipper-cursor-buddy/` | [Cursor adapter README](flipper-cursor-buddy/README.md) | local IPC |
| **Claude Desktop** | *(none — built into FAP)* | [Desktop mode](#claude-desktop-ble) | BLE only |

Each CLI adapter currently uses its agent's native hook or App Server interface. They share the Flipper application and wire protocol; consolidating duplicated host transport and queue code into one core is in progress.

> **Important:** Only one bridge should use the Flipper USB serial port at a time. Stop or disable other bridges before switching agents.

## Flipper app modes

Flipper Agent Buddy runs in one of two integration modes, switchable from the on-device menu (long-press **Right → MENU**, then the top row):

- **Agent Bridge (USB/BLE)** (default) — connects a compatible coding-agent adapter over USB or BLE. The adapter reports supported controls and approval types.
- **Claude Desktop (BLE)** — talks directly to the Claude Desktop app over Anthropic's [Hardware Buddy](https://github.com/anthropics/claude-desktop-buddy) protocol. No plugin, no host bridge. Live session status, token counts, transcript, and on-device permission prompts.

See [flipper-app/README.md](flipper-app/README.md) for the full button map and mode details.

## Buttons

| Button | Action (Bridge mode) |
|--------|----------------------|
| UP | Start / stop voice dictation (host dependent) |
| UP (hold) | Hold Space for voice input (terminal forwarding) |
| LEFT | Interrupt (adapter or Esc fallback) |
| LEFT (hold) | Send Ctrl+C to active terminal |
| RIGHT | Open command menu |
| RIGHT (hold) | Open info menu |
| OK | Submit Enter to active terminal; answer the displayed approval/choice when one is open |
| OK (hold) | Type "yes" and submit |
| DOWN | Send Down arrow to active terminal; navigate choices when displayed |
| DOWN (hold) | Toggle mute |
| BACK | Send Backspace; defer/close the displayed request where supported |
| BACK (hold) | Exit |

## Setup

### 1. Install the Flipper app

Download `claude_buddy.fap` from the [latest release](../../releases/latest) or build from source:

```bash
cd flipper-app && ufbt build
# Flash to a connected device (stop any running bridge first):
ufbt launch
```

Copy the `.fap` to `apps/Bluetooth/` on the SD card, or flash via `ufbt launch`.

Launch **Applications → Bluetooth → Agent Buddy** on the Flipper. You should hear the startup fanfare when the transport connects.

### 2. Pick your CLI agent

#### Claude Code

> **Requires Python 3.10+.**

```bash
claude plugin marketplace add MrDaila007/flipper-agent-buddy
claude plugin install flipper-agent-buddy-claude@flipper-agent-buddy
```

The plugin starts the host bridge automatically on each Claude Code session. Configure transport in the plugin settings (`auto`, `usb`, or `ble`).

Permission prompts are shown one at a time in FIFO order, including prompts
from parallel tool calls. Each Flipper decision is tied to the displayed prompt;
stale replies cannot approve the next request. The detail shows the requested
command, file path, or MCP operation parameters (parameter names only), with
common inline credentials redacted from shell commands. If the Flipper is
unavailable or the request times out, Claude's normal permission flow remains
available.

#### OpenAI Codex

```bash
./flipper-codex-buddy/scripts/install-codex-plugin.sh
```

Then open `/hooks` in Codex, trust the Flipper Agent Buddy adapter hooks, and start a new thread. See [flipper-codex-buddy/README.md](flipper-codex-buddy/README.md).

#### Cursor

```bash
chmod +x flipper-cursor-buddy/scripts/install-cursor-hooks.sh
./flipper-cursor-buddy/scripts/install-cursor-hooks.sh
```

Open **Settings → Hooks** in Cursor, confirm hooks are loaded, and start a new agent session. See [flipper-cursor-buddy/README.md](flipper-cursor-buddy/README.md).

### Claude Desktop (BLE)

1. On the Flipper, switch to **Claude Desktop (BLE)** in the info menu.
2. In Claude Desktop: **Help → Troubleshooting → Enable Developer Mode**.
3. **Developer → Open Hardware Buddy** and select your Flipper. Grant Bluetooth permission on first connect.

Once paired, Claude Desktop auto-reconnects when both sides are online.

## Connection

CLI bridges connect over USB (plug-and-play) or Bluetooth LE. USB is preferred when the cable is plugged in; bridges fall back to BLE automatically when configured for `auto`.

**macOS — Bluetooth pairing:** accept the pairing prompt on first BLE connect. If pairing fails after a firmware flash, remove the Flipper from System Settings → Bluetooth and re-pair.

**macOS — Accessibility (keystroke forwarding):** grant your terminal app Accessibility permission in System Settings → Privacy & Security → Accessibility. Without it, status updates work but button presses do nothing.

**Linux — USB:** Flipper appears as `/dev/ttyACM*`. Add your user to `dialout` if you get permission errors:

```bash
sudo usermod -aG dialout $USER   # log out and back in
export FLIPPER_TRANSPORT=usb     # recommended on Linux
```

**Linux — Keystroke forwarding:** requires `xdotool` on X11 (`sudo apt install xdotool`). Wayland is not yet supported.

**Linux — BLE:** experimental; USB is the reliable path today.

## Host identification protocol

Bridges report the connected agent in the `agent` field and its display identity in `host` on `state` messages:

```json
{"v":1,"t":"state","d":{"agent":true,"claude":true,"host":"cursor"}}
```

`host` is a short display label such as `claude`, `codex`, or `cursor`; other ASCII labels are accepted. `claude` remains in the example for compatibility with older FAPs. Older bridges without `host` still work; Desktop BLE mode defaults to **Claude**.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Flipper not found over USB | Stop other bridges and apps using the serial port (qFlipper, another agent bridge). Set `FLIPPER_SERIAL_PORT` explicitly. |
| Wrong agent label / no label | Restart the bridge after flashing a new FAP. Ensure the bridge sends `host` in `state` messages. |
| No sound on task complete | Check bridge log: `tail -f /tmp/<agent>-flipper-bridge.log` |
| Buttons do nothing (macOS) | Grant Accessibility permission to your terminal app. |
| Buttons do nothing (Linux) | Install `xdotool`; focus the terminal window. |
| Parse errors / CLI banner in log | The Flipper is running the CLI app, not Agent Buddy — open the Agent Buddy FAP and restart the bridge. |

Bridge logs:

| Agent | Log file |
|-------|----------|
| Claude Code | `/tmp/claude-flipper-bridge.log` |
| Codex | `/tmp/codex-flipper-bridge.log` |
| Cursor | `/tmp/cursor-flipper-bridge.log` |

## Repository layout

```
flipper-app/              Flipper Zero FAP (C)
plugin/                   Claude Code plugin + host bridge
flipper-codex-buddy/      Codex adapter package
flipper-cursor-buddy/     Cursor adapter package
```

## Development

See [CLAUDE.md](CLAUDE.md) for build commands, architecture, protocol details, and release checklist.

## Support

For issues and project discussions, use the repository's GitHub Issues and Discussions pages.

## License

MIT — see [LICENSE](LICENSE).
