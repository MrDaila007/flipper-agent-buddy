#!/usr/bin/env python3
"""postToolUseFailure hook: error sound on the Flipper."""

import json
import os
import socket
import sys

SOCKET_PATH = "/tmp/cursor-flipper-bridge.sock"


def send_to_flipper(sound: str, text: str = "", subtext: str = "") -> None:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(1.0)
    s.connect(SOCKET_PATH)
    msg = json.dumps({"action": "notify", "sound": sound, "vibro": True, "text": text, "subtext": subtext})
    s.sendall(msg.encode())
    s.shutdown(socket.SHUT_WR)
    s.recv(4096)
    s.close()


def extract_subtext(hook_input: dict) -> str:
    error = hook_input.get("error_message") or hook_input.get("error", "")
    tool_name = hook_input.get("tool_name", "")
    tool_input = hook_input.get("tool_input") or {}

    if tool_name in ("Shell", "Bash"):
        for line in str(error).splitlines():
            line = line.strip()
            if line.startswith("Exit code"):
                continue
            if line:
                return line[:21]

    if tool_name in ("Write", "Edit", "Read"):
        path = tool_input.get("path") or tool_input.get("file_path", "")
        if path:
            return os.path.basename(path)[:21]

    for line in str(error).splitlines():
        line = line.strip()
        if line:
            return line[:21]
    return "Failed"


def main():
    if not os.path.exists(SOCKET_PATH):
        sys.exit(0)

    try:
        hook_input = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    tool_name = hook_input.get("tool_name", "Tool")
    shown = "MCP" if str(tool_name).startswith("MCP:") else tool_name
    subtext = extract_subtext(hook_input)

    try:
        send_to_flipper("error", f"{shown} failed", subtext)
    except Exception:
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
