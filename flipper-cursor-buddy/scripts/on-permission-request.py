#!/usr/bin/env python3
"""preToolUse hook: show permission request on Flipper, return Cursor decision."""

import json
import os
import socket
import sys

SOCKET_PATH = "/tmp/cursor-flipper-bridge.sock"
TIMEOUT = 60
PENDING_COMPACT_FLAG = "/tmp/cursor-flipper-pending-compact.flag"


def send_to_bridge(tool: str, detail: str) -> dict:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(TIMEOUT)
    s.connect(SOCKET_PATH)
    msg = json.dumps({"action": "permission_request", "tool": tool, "detail": detail})
    s.sendall(msg.encode())
    s.shutdown(socket.SHUT_WR)
    resp = s.recv(4096)
    s.close()
    return json.loads(resp.decode())


def extract_detail(tool_name: str, tool_input: dict) -> str:
    if tool_name.startswith("MCP:"):
        return tool_name[4:].strip()[:21]
    if tool_name in ("Shell", "Bash"):
        cmd = tool_input.get("command", "")
        return cmd[:21] if cmd else ""
    if tool_name in ("Write", "Edit", "Read"):
        path = tool_input.get("path") or tool_input.get("file_path", "")
        return os.path.basename(path)[:21] if path else ""
    if tool_name in ("WebFetch", "WebSearch"):
        val = tool_input.get("url") or tool_input.get("search_term") or tool_input.get("query", "")
        for prefix in ("https://", "http://"):
            if isinstance(val, str) and val.startswith(prefix):
                val = val[len(prefix):]
                break
        return str(val)[:21]
    if tool_name == "Task":
        return str(tool_input.get("description", ""))[:21]
    return ""


def display_tool(tool_name: str) -> str:
    if tool_name.startswith("MCP:"):
        return "MCP"
    return tool_name or "Tool"


def main():
    if not os.path.exists(SOCKET_PATH):
        sys.exit(1)

    try:
        hook_input = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        sys.exit(1)

    tool_name = hook_input.get("tool_name", "Unknown")
    tool_input = hook_input.get("tool_input") or {}
    detail = extract_detail(tool_name, tool_input)
    shown = display_tool(tool_name)

    try:
        result = send_to_bridge(shown, detail)
    except Exception:
        sys.exit(1)

    status = result.get("status")
    if status == "ask" or status != "ok":
        sys.exit(1)

    if result.get("allowed", False):
        print(json.dumps({"permission": "allow"}))
    else:
        print(json.dumps({
            "permission": "deny",
            "user_message": "Denied on Flipper",
        }))
    sys.exit(0)


if __name__ == "__main__":
    main()
