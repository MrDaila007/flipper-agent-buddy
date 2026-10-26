## v1.0.0 — 2026-10-26

- Context-driven character animations (Working, Compacting, Denied, Stressed, Overloaded, Critical, RateLimited).
- Ctx / Lim usage meters when the host reports context pressure.
- Sound-to-pose mapping for compaction, tool beats, and permission outcomes.
- Host label in the status header (`Claude` / `Codex` / `Cursor`) via `state.host` protocol field.
- Marquee scroll for status text that exceeds display width.

## v0.6

- Fixed connection/disconnection state handling in Bridge mode.
- Fixed a memory leak in the Flipper app.


## v0.5

- New **Claude Desktop (BLE)** mode: talks directly to the Claude Desktop app over Anthropic's Hardware Buddy protocol. No plugin needed.
- Linux support for the host bridge plugin — thanks to @DanilaE for the contribution!
- Info menu relabels: **Claude Code (USB/BLE)** / **Claude Desktop (BLE)**.
- Help and Transcript pages are now mode-aware.
- Changed Flipper app category from USB to Bluetooth.


## v0.4

- Info menu (Hold ►): Help, Transcript, Plan/Code Mode, About.
- Transcript scrolling with Page Up/Down and jump-to-top/bottom.
- Flipper notifications for tool failures and elicitation prompts.

## v0.3

- Auto-discover slash commands from user/project commands, skills, and enabled plugins.
- Selected menu commands are promoted to the top of the list for convenient re-use.

## v0.2

- Routed remote input to the active runner session, including the correct terminal tab.
- Added Up-button long-press support for Claude voice input.
- Fixed BLE signal bars in the header.
- Fixed slash-command menu refresh so the first selected command matches the item shown on screen.

## v0.1

- Initial release with physical remote control, haptic feedback, USB/BLE transport, and Claude Code plugin integration.
# 1.0 — Flipper Agent Buddy

- Rebrand the universal FAP as **Agent Buddy** while preserving the app ID and
  persisted settings path for in-place upgrades.
- Rename the generic host mode to **Agent Bridge (USB/BLE)** and keep the
  connected provider name in the status header.
- Clarify the shared host protocol and support for Claude Code, Codex, Cursor,
  and future adapters.
