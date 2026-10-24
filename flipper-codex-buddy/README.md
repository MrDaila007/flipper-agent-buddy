# Flipper Codex Buddy

Codex integration connecting the existing Flipper Zero buddy application to a
running Codex App Server over a local Unix socket, with USB or Bluetooth to Flipper.

## Features

- One FIFO attention queue for all loaded Codex sessions
- Yes/no replies and selection from agent-provided answer options, independent of window focus
- Automatic removal when a request is answered in Codex, cancelled, or its turn ends
- Overview of session count and activity; no session selection required
- Optional PC diagnostics for individual sessions

## Native attention queue

The default `FLIPPER_CONTROL_BACKEND=app-server` connects to your existing local
Codex App Server. It discovers loaded sessions and attaches to their event
streams using `thread/resume` without configuration overrides. It does not start
threads. Turn-starting commands run only after an explicit Flipper selection.
Sessions in an independent standalone CLI runtime won't appear unless they
share this App Server.

The daemon owns the queue, session routing, duplicate suppression, and replies.
Flipper renders the existing permission/menu screens and echoes the request/view ID.
The main screen shows the number of sessions and how many are busy. A request
opens automatically with its queue count, session indicator/name, and a short
summary. The current firmware uses ASCII; Russian display text is transliterated.
Answers sent to Codex retain their original Unicode labels.

- **OK / Allow** answers yes to the displayed request.
- **Back / Deny** or **Left / Cancel** answers no to that request.
- After Codex resolves it, the next queued request appears automatically.
- When the queue is empty, the overview returns.

The command menu also lists `/compact`, `/interrupt`, and enabled Codex skills
discovered through `skills/list`. Skills are sent as typed App Server inputs.
Commands target the only active session, or the only loaded session when none is
active; ambiguous targets require selecting a session from the PC diagnostics.
Context and account limit meters use App Server token-usage and rate-limit
updates. Flipper alerts when either reaches 80% and again at 95%.

Supported binary requests include command/file approvals, requested permission
grants (for the current turn only), and single questions with explicit yes/no
options. Other questions with selectable options automatically open the existing
menu view with the question and numbered options:

- **Up/Down** moves between options; **OK / Choose** selects the displayed option.
- Several questions in one request appear in sequence. The daemon submits one
  complete answer after the last question; it never sends partial answers.
- Long option lists have **Next options** / **Previous options** pages.
- **Back / Later** defers the request locally without choosing an answer. Use
  Right → **Attention queue** to reopen it; earlier selections in the same batch
  are retained while the request is pending.
- Free-form text, secret input, or external login flows still show **Needs input
  on PC**. No answer is invented for them.

Display labels and question text are shortened to fit the screen. Original full
option labels are mapped by index on the PC, so equal/truncated display prefixes
cannot redirect an answer. A new opaque view ID is used for each question/page;
a stale selection cannot answer the next question.

Decisions carry an opaque request token, mapped to the original server request,
thread and turn. Late/idless/duplicate button replies cannot answer the next
request. Codex's `serverRequest/resolved` notification closes the queue item;
the normal application UI remains available and can answer first. Unconfirmed
decisions are never automatically replayed. On disconnect tokens are invalidated;
reconnection reattaches to loaded sessions for server replay of pending requests.

Use the updated **Applications → Bluetooth → Claude Buddy** copy. An older copy
may still be present under USB; that copy does not support these additions.
The application folder is independent of using USB or BLE as the transport.

Update the Flipper FAP along with the daemon: it must advertise `perm_ids` in its
pong responses. Older FAPs display an update notice and cannot approve this queue.
Choice support additionally requires `choice_ids` in pong responses. It adds
a generic `choice` message (view ID, title, question, pipe-delimited options) and
`choice_resp` (same ID plus zero-based index, or -1 to defer). The existing menu
view is reused; queue/routing logic stays on the PC. There is no session
navigation UI.

Start the daemon from the repository Python environment:

```sh
python -m bridge --transport usb
```

PC diagnostics use Buddy's IPC socket:

```sh
python -m bridge.agent_cli sessions
python -m bridge.agent_cli attention
# Optional advanced controls, unrelated to the attention queue:
python -m bridge.agent_cli select <full-thread-id>
python -m bridge.agent_cli status
python -m bridge.agent_cli interrupt
```

Checked with Codex CLI 0.145.0 and App Server 0.164.0. See the
[official App Server protocol](https://learn.chatgpt.com/docs/app-server).

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
export FLIPPER_CONTROL_BACKEND=app-server  # default; keyboard explicitly enables legacy input
# export FLIPPER_CODEX_SOCKET=/path/to/app-server.sock  # optional override
```

Leave `FLIPPER_CODEX_SOCKET` unset to use
`${CODEX_HOME:-~/.codex}/app-server-control/app-server-control.sock`. Do not set it
to an empty string. It is a Unix WebSocket socket, separate from Buddy's hook IPC
socket. No network listener or additional API key is needed to attach to your
already authenticated local server.

The Flipper status header shows **Codex** when this bridge is connected.

The plugin stores its virtual environment and detected Bluetooth name under
`PLUGIN_DATA`. Its IPC socket and transient state live in a user-private runtime
directory (`$XDG_RUNTIME_DIR/flipper-codex-buddy` or the per-user directory
`/tmp/flipper-codex-buddy-UID`). Set `FLIPPER_RUNTIME_DIR` to override it or
`FLIPPER_BRIDGE_SOCKET` to override only the socket path.
For BLE, pair the Flipper with the host and set `FLIPPER_BT_ADDRESS` to its
Bluetooth address to pin the daemon to that device. Without an explicit pin,
the first connection requests pairing and stores the resulting address in the
private runtime directory; verify the code shown on the Flipper before
accepting. Later connections use the saved bond without initiating pairing
again. If you set an explicit address, pair the device with the OS first.

## Security boundaries

- Buddy IPC is local-only, limited to 64 KiB per request, checks the Linux peer
  UID where available, and uses a user-owned runtime directory with mode `0700`
  plus a socket with mode `0600`. Existing paths are checked before replacement.
- BLE pairing is requested by default. After a successful first pairing, the
  Flipper address is pinned in the private runtime directory; set
  `FLIPPER_BT_ADDRESS` to pin it explicitly. USB remains the safer transport
  when Bluetooth pairing cannot be verified.
- The Flipper protocol still has no application-level message authentication.
  The bridge-mode SDK serial profile's encryption requirements have not been
  verified here. Treat BLE as untrusted until that link is confirmed encrypted;
  a local attacker with access to the user's account can also reach the Codex
  App Server and the private IPC socket.
- Permission replies are bound to opaque request IDs and the original server
  request. A stale or duplicate Flipper response cannot approve a later item.
Bridge enablement is persisted in `PLUGIN_DATA/bridge-enabled` and can be
changed with the Codex slash commands `/bridge`, `/bridge-on`, `/bridge-off`,
and `/bridge-status`.

## Codex hooks

The following hook-driven controls apply to explicit legacy mode
(`FLIPPER_CONTROL_BACKEND=keyboard`). Native mode uses App Server events and a shared attention queue instead;
it remains running when individual sessions end. Legacy input uses platform GUI
automation and can depend on terminal focus.

After installation, open `/hooks` in Codex and trust the plugin hook definition.
In legacy mode the plugin handles `SessionStart` (including forked threads), `SessionEnd`,
`Interrupt`, `UserPromptSubmit`, `PermissionRequest`, `PostToolUse`, compaction,
subagent lifecycle, and `Stop`. Session tracking uses Codex thread IDs, so
resuming or compacting a thread does not create a duplicate bridge session.

Codex hooks currently support one-shot allow/deny decisions. The Flipper
"Always" choice is therefore treated as a one-shot allow in this plugin.
