# Flipper Agent Buddy (Flipper app)

Flipper Agent Buddy turns your Flipper Zero into a physical remote and status display for coding agents, with haptic, audio, and LED feedback plus a shared interface for common actions.

One FAP works with host adapters for **Claude Code**, **Codex**, and **Cursor**, plus **Claude Desktop** over BLE. Additional agents can use the shared host protocol.

## Display

| Element | Description |
|---------|-------------|
| **Host label** | Top-left: the connected agent name (from bridge `state.host`) |
| **Transport** | Top-right: `USB` or BLE signal bars |
| **Session dot** | Filled circle when an agent session is active |
| **Character** | Animated poses for idle, working, compaction, errors, permissions, context pressure |
| **Ctx / Lim meters** | Optional usage bars when the host reports context/session pressure |
| **Status text** | Primary line + optional subtext; long text scrolls as a marquee |

## Two modes

Pick the bridge mode for a coding agent or the direct Claude Desktop BLE mode. Switch on-device at any time: long-press **Right → MENU**, then the top row.

| Mode | Pairs with | Transport | What the buttons do |
|------|------------|-----------|---------------------|
| **Agent Bridge (USB/BLE)** *(default)* | Any compatible host adapter (Claude Code / Codex / Cursor) | USB or BLE | Agent status, permissions, choices, and supported button actions |
| **Claude Desktop (BLE)** | Claude Desktop app via [Hardware Buddy](https://github.com/anthropics/claude-desktop-buddy) | BLE only | Live session status + transcript; Allow / Deny permission prompts on-device |

Both modes share the same LED, sound, and vibration feedback patterns.

## Mode 1 — CLI agents (USB/BLE)

**Setup**

1. Install and launch Flipper Agent Buddy on your Flipper.
2. Install the host bridge for your agent ([root README](../README.md#2-pick-your-cli-agent)).
3. Start an agent session. The bridge connects automatically (or run `flipper-*-buddy/bin/flipper-bridge enable` for Codex/Cursor).

**Connection.** USB when the cable is plugged in; otherwise BLE (if supported on your host OS). Only one bridge should hold the serial port at a time.

**Button map**

| Button | Action |
|--------|--------|
| UP | Start / stop voice dictation |
| UP (hold) | Hold Space for voice input |
| LEFT | Interrupt (Esc) |
| LEFT (hold) | Send Ctrl+C |
| RIGHT | Open command menu |
| RIGHT (hold) | Open info menu |
| OK | Submit Enter |
| OK (hold) | Type "yes" and submit |
| DOWN | Send Down arrow |
| DOWN (hold) | Toggle mute |
| BACK | Send Backspace |
| BACK (hold) | Exit app |

## Mode 2 — Claude Desktop (BLE)

Talks directly to Claude Desktop over BLE — no plugin, no Python bridge.

**Setup**

1. On the Flipper, long-press **Right → MENU** and select **Claude Desktop (BLE)**.
2. In Claude Desktop: **Help → Troubleshooting → Enable Developer Mode**.
3. **Developer → Open Hardware Buddy** and select your Flipper. Accept the Bluetooth permission prompt.

**What you see**

- Running / waiting session counts and heartbeat status
- Recent transcript lines (TRANSCRIPT view)
- Permission prompts — Allow or Deny on-device
- Host label shows **Claude** when connected

**Button map** (no keystroke forwarding over this protocol)

| Button | Action |
|--------|--------|
| RIGHT / RIGHT (hold) | Open info menu |
| OK | Allow permission |
| LEFT | Deny permission |
| DOWN (hold) | Toggle mute |
| BACK (hold) | Exit app |

The in-app **HELP** page reflects whichever mode is active.

## Build

```bash
# Requires ufbt: pip3 install ufbt
ufbt build
ufbt launch    # flash to connected Flipper (stop bridges first)
```

See [CHANGELOG.md](CHANGELOG.md) for release history.
