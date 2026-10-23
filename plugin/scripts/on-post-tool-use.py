#!/usr/bin/env python3
"""PostToolUse hook: plays a per-tool sound on the Flipper after each tool call."""

import json
import os
import socket
import sys

SOCKET_PATH = "/tmp/claude-flipper-bridge.sock"
STATS_PATH = "/tmp/claude-flipper-turn-stats.json"

# Map tool names (or prefixes) to sound names.
# Evaluated in order — first match wins.
TOOL_SOUNDS = [
    ({"Edit", "Write", "NotebookEdit"},         "enter"),   # file write: soft blip
    ({"Bash"},                                   "cmd"),     # shell command: confirm tone
    ({"WebFetch", "WebSearch"},                  "alert"),   # network: attention tone
    ({"Read"},                                   "enter"),   # read-only: soft blip
    ({"Glob", "Grep"},                           None),   # read-only: soft blip
]


def sound_for_tool(tool_name: str) -> str | None:
    for tools, sound in TOOL_SOUNDS:
        if tool_name in tools:
            return sound
    return None  # unknown tools: silent


def pose_for_tool(tool_name: str) -> str:
    name = tool_name.lower()
    if name in {"read", "glob", "grep"}:
        return "reading"
    if name in {"edit", "write", "apply_patch", "notebookedit"}:
        return "editing"
    if name in {"bash", "shell"}:
        return "terminal"
    if name in {"webfetch", "websearch"}:
        return "searching"
    if name in {"agent", "task"} or name.startswith("mcp__"):
        return "delegating"
    return "thinking"


def send_to_flipper(sound: str, text: str = "", subtext: str = "", pose: str | None = None) -> None:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(1.0)
    s.connect(SOCKET_PATH)
    payload = {"action": "notify", "sound": sound, "vibro": False, "text": text, "subtext": subtext}
    if pose:
        payload["pose"] = pose
    msg = json.dumps(payload)
    s.sendall(msg.encode())
    s.shutdown(socket.SHUT_WR)
    s.recv(4096)
    s.close()


def tool_detail(tool_name: str, hook_input: dict) -> str:
    """Extract a short detail string from the tool input."""
    tool_input = hook_input.get("tool_input", {})
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        return cmd[:21] if cmd else ""
    if tool_name in ("Edit", "Write", "Read"):
        path = tool_input.get("file_path", "")
        return os.path.basename(path)[:21] if path else ""
    if tool_name in ("WebFetch", "WebSearch"):
        val = tool_input.get("url") or tool_input.get("query", "")
        for prefix in ("https://", "http://"):
            if val.startswith(prefix):
                val = val[len(prefix):]
                break
        return val[:21]
    return ""


def main():
    if not os.path.exists(SOCKET_PATH):
        sys.exit(0)

    try:
        hook_input = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    tool_name = hook_input.get("tool_name", "")

    # Skip notification for Bash commands that write to the Flipper socket directly
    # (e.g. the flipper-notify skill) — they already set their own display.
    # Also flag the stop hook to skip "Turn complete" for this turn.
    if tool_name == "Bash":
        cmd = hook_input.get("tool_input", {}).get("command", "")
        if SOCKET_PATH in cmd:
            try:
                open("/tmp/claude-flipper-skip-stop.flag", "w").close()
            except Exception:
                pass
            sys.exit(0)

    # Track tool usage stats for the Stop hook summary
    try:
        stats = json.loads(open(STATS_PATH).read()) if os.path.exists(STATS_PATH) else {}
    except Exception:
        stats = {}
    stats[tool_name] = stats.get(tool_name, 0) + 1
    try:
        open(STATS_PATH, "w").write(json.dumps(stats))
    except Exception:
        pass

    sound = sound_for_tool(tool_name)
    detail = tool_detail(tool_name, hook_input)
    try:
        send_to_flipper(sound or "none", tool_name, detail, pose_for_tool(tool_name))
    except Exception:
        pass

    try:
        import subprocess

        subprocess.run(
            [sys.executable, os.path.join(os.path.dirname(__file__), "context_usage.py"), "sync"],
            input=json.dumps(hook_input).encode("utf-8"),
            timeout=2,
            check=False,
        )
    except Exception:
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
