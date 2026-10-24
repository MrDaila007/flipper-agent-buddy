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
- Native attention queue across loaded App Server sessions, with no session selection required
- Addressed yes/no responses, duplicate suppression, and external/cancelled request removal
- Choice questions: numbered options, multi-question batches, pagination, and stale-view protection
- Native Codex command menu: `/compact`, `/interrupt`, and enabled skills from `skills/list`
- Context and account quota indicators from App Server usage events, with alerts at 80% and 95%
- Minimal FAP protocol extension: request token echo, `perm_ids`/`choice_ids`, `choice_resp`, and `perm_clear`
- Native tests cover multi-session FIFO, stale answers, duplicates, disconnects, binary questions,
  and optional turn-specific interrupt diagnostics

## Next

- Free-form/secret questions still need the normal Codex application UI

- Trust hooks in Codex (`/hooks`) after install on fresh machines
- Re-run permission approval from a Codex session started after marketplace install
- Optionally expose bridge toggle outside slash commands alone
