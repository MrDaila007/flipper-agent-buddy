#!/usr/bin/env python3
"""PostToolUse hook: per-tool sound, context meters, and post-compact cue."""

import json
import os
import socket
import sys

SOCKET_PATH = "/tmp/cursor-flipper-bridge.sock"
STATS_PATH = "/tmp/cursor-flipper-turn-stats.json"
SKIP_STOP_FLAG = "/tmp/cursor-flipper-skip-stop.flag"
PENDING_COMPACT_FLAG = "/tmp/cursor-flipper-pending-compact.flag"

TOOL_SOUNDS = [
    ({"Write", "Edit", "apply_patch"}, "enter"),
    ({"Shell", "Bash"}, "cmd"),
    ({"WebFetch", "WebSearch"}, "alert"),
    ({"Read"}, "enter"),
    ({"Glob", "Grep"}, None),
]


def sound_for_tool(tool_name: str) -> str | None:
    for tools, sound in TOOL_SOUNDS:
        if tool_name in tools:
            return sound
    return None


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
    if name == "task" or name.startswith("mcp:"):
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
    tool_input = hook_input.get("tool_input") or {}
    if tool_name in ("Shell", "Bash"):
        return str(tool_input.get("command", ""))[:21]
    if tool_name in ("Write", "Edit", "Read"):
        path = tool_input.get("path") or tool_input.get("file_path", "")
        return os.path.basename(path)[:21] if path else ""
    if tool_name in ("WebFetch", "WebSearch"):
        val = tool_input.get("url") or tool_input.get("search_term") or tool_input.get("query", "")
        return str(val)[:21]
    return ""


def display_name(tool_name: str) -> str:
    if tool_name.startswith("MCP:"):
        return "MCP"
    return tool_name or "Tool"


def maybe_finish_compact() -> None:
    if not os.path.exists(PENDING_COMPACT_FLAG):
        return
    try:
        os.remove(PENDING_COMPACT_FLAG)
        send_to_flipper("compact_done", "Compacted", "")
    except Exception:
        pass


def main():
    if not os.path.exists(SOCKET_PATH):
        sys.exit(0)

    try:
        hook_input = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    tool_name = hook_input.get("tool_name", "")
    shown_name = display_name(tool_name)

    if tool_name in ("Shell", "Bash"):
        cmd = (hook_input.get("tool_input") or {}).get("command", "")
        if SOCKET_PATH in cmd:
            try:
                open(SKIP_STOP_FLAG, "w").close()
            except Exception:
                pass
            sys.exit(0)

    maybe_finish_compact()

    try:
        stats = json.loads(open(STATS_PATH).read()) if os.path.exists(STATS_PATH) else {}
    except Exception:
        stats = {}
    stats[shown_name] = stats.get(shown_name, 0) + 1
    try:
        open(STATS_PATH, "w").write(json.dumps(stats))
    except Exception:
        pass

    sound = sound_for_tool(tool_name)
    try:
        send_to_flipper(sound or "none", shown_name, tool_detail(tool_name, hook_input), pose_for_tool(tool_name))
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
