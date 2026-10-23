# Flipper Codex Buddy — status

Last updated: 2026-10-23

## Done

- Codex plugin package in `flipper-codex-buddy/`
- Host bridge adapted for Codex sockets, hook payloads, and permission flow
- `HOST_TYPE=codex` in `state` messages for Flipper host label
- Flipper hardware handshake verified over USB
- Permission approval from Flipper works end to end
- Persisted bridge enable/disable flag and Codex slash commands:
  - `/bridge`
  - `/bridge-on`
  - `/bridge-off`
  - `/bridge-status`
- Local Codex marketplace at `.agents/plugins/marketplace.json` (`flipper-local`)
- Install script: `scripts/install-codex-plugin.sh`
- Bridge defaults to **enabled** when `PLUGIN_DATA/bridge-enabled` is missing
- Python tests passing (`pytest` in `host-bridge/tests/`)
- Current Codex `SessionEnd`, `Interrupt`, forked-session, and post-tool error hook support
- Session tracking by Codex thread ID (resume and compaction are idempotent)

## Next

- Trust hooks in Codex (`/hooks`) after install on fresh machines
- Re-run permission approval from a Codex session started after marketplace install
- Optionally expose bridge toggle outside slash commands alone
