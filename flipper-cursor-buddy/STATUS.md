# Flipper Cursor Buddy — status

Last updated: 2026-10-23

## Done

- Cursor hook package in `flipper-cursor-buddy/`
- `.cursor/hooks.json` with session, tool, compaction, subagent, and stop hooks
- Host bridge with `/tmp/cursor-flipper-bridge.sock`, `cursor_connect`, and `HOST_TYPE=cursor`
- Install script: `scripts/install-cursor-hooks.sh`
- `preToolUse` permission flow with Cursor-native `permission` JSON output
- Current subagent hook fields and required `preToolUse`/`beforeSubmitPrompt` responses
- Post-compact signaling via pending flag on first `postToolUse` (Cursor has no `postCompact` hook)
- Hardware verified: USB on Linux, host label **Cursor** in Flipper header, ping/pong stable
- Python tests passing (`pytest` in `host-bridge/tests/`)

## Next

- End-to-end `preToolUse` approval flow test in a live Cursor agent session
- Document bridge enable/disable in main README (done — see root README)
- BLE transport on Linux (inherits upstream limitation)
