# Flipper Agent Buddy architecture

Flipper Agent Buddy is being shaped into a universal Flipper companion. The
firmware and device protocol do not depend on a particular coding agent.
Agent-specific behavior belongs behind host-side adapters.

## Migration status

The FAP and wire protocol already serve Claude Code, Codex, and Cursor bridges.
The host bridge implementations are still separate packages with duplicated
transport and daemon code. The shared core described below is the target; the
work ahead is to extract it incrementally while keeping each agent adapter
installable and preserving existing Claude Desktop BLE support.

## Layers

### Flipper application

The FAP owns buttons, screens, sound, vibration, LEDs, USB/BLE transport, and
the wire protocol. It renders normalized status and attention messages. It does
not know how Claude Code, Codex, Cursor, or another agent represents a session
or asks for permission.

Claude Desktop is a direct BLE integration using Anthropic's Hardware Buddy
protocol. It remains a distinct adapter because the desktop application speaks
that protocol directly to the FAP rather than through the host bridge.

### Shared host core

The shared core owns transport selection, Flipper protocol framing, private
local IPC, session and activity state, attention FIFO, request correlation,
timeouts, stale-reply protection, and capability negotiation. It presents one
stable interface to the Flipper regardless of which agent is connected.

### Agent adapters

An adapter translates a provider's native interface into the shared event and
request model. Initial adapters are Claude Code hooks, Codex App Server, and
Cursor hooks. New agents should be addable without changing firmware or the
shared queue.

An adapter reports capabilities rather than assuming that every agent supports
the same actions. Capabilities include session discovery, interrupt, free-form
input, selectable questions, one-shot approval, session-scoped approval,
persistent policy amendments, context usage, and account limits.

## Normalized host model

Adapters emit events with an agent ID, session ID, optional turn ID, event kind,
display title/detail, and optional usage values. Events include connection,
session state, work started/stopped, compaction, tool activity, notifications,
and errors.

Attention requests carry an opaque request ID, agent/session/turn identity,
display text, expiry policy, and the exact decisions offered by the agent.
Answers are routed back through the originating adapter using that request ID.
The core never invents a decision that the agent did not offer. Queue entries
are removed when answered, cancelled, expired, or resolved elsewhere.

## Permission and answer model

The common UI exposes only actions the adapter declares for that request:

- one-time allow and deny;
- session-scoped allow when the agent offers it;
- a specific persistent rule when the agent provides its exact scope;
- selectable answers for explicit non-secret questions;
- defer to the agent's own UI when Flipper cannot safely answer.

“Always” is not a universal protocol value. The adapter maps a device choice to
the exact native decision and scope, such as Claude's `updatedPermissions` or a
Codex App Server decision. The screen must identify the scope before the user
confirms it.

## Compatibility and safety

The host and FAP negotiate protocol capabilities at connection time. Unknown
messages are ignored; unsupported decisions fall back to the agent's normal
UI. Every actionable response is bound to one live request ID. Disconnects,
duplicate replies, expired requests, and replies for another session cannot be
replayed against a later queue item.

The host core keeps local IPC in a user-private runtime directory. Agent
credentials stay with the agent's own authenticated runtime; the bridge does
not collect or store provider API keys.

## Repository boundaries

The repository is the canonical source for the FAP, shared core, agent
adapters, and install packages. Provider-specific packages contain only their
adapter, hooks/plugin metadata, and setup needed to register that adapter.
Generated packages and release artifacts are built from this source tree.
