#!/usr/bin/env python3
"""PermissionRequest hook: shows permission request on Flipper, waits for user decision."""

import json
import os
import re
import socket
import sys

SOCKET_PATH = "/tmp/claude-flipper-bridge.sock"
TIMEOUT = 64  # daemon returns or falls back before the 65s Claude hook timeout


def send_to_bridge(tool: str, detail: str, hook_input: dict) -> dict:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(TIMEOUT)
    s.connect(SOCKET_PATH)
    msg = json.dumps({
        "action": "permission_request", "tool": tool, "detail": detail,
        "session_id": hook_input.get("session_id", ""),
        "cwd": hook_input.get("cwd", ""),
        "allow_always": bool(hook_input.get("permission_suggestions")),
    })
    s.sendall(msg.encode())
    s.shutdown(socket.SHUT_WR)
    resp = s.recv(4096)
    s.close()
    return json.loads(resp.decode())


def extract_detail(tool_name: str, tool_input: dict) -> str:
    """Extract useful, bounded context without exposing arbitrary MCP values."""
    if "__" in tool_name:
        parts = tool_name.split("__")
        if len(parts) >= 3:
            keys = [str(key) for key in tool_input if not _sensitive_key(str(key))]
            suffix = ", ".join(keys[:3])
            return (f"{parts[-1]} ({suffix})" if suffix else parts[-1])[:63]
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        desc = tool_input.get("description", "")
        value = cmd.strip() or desc.strip()
        value = _redact_command(value)
        return value.replace("\n", " ")[:63] if value else ""
    if tool_name in ("Edit", "Write", "Read"):
        path = tool_input.get("file_path", "")
        return str(path)[-63:] if path else ""
    if tool_name in ("WebFetch", "WebSearch"):
        val = tool_input.get("url") or tool_input.get("query", "")
        for prefix in ("https://", "http://"):
            if val.startswith(prefix):
                val = val[len(prefix):]
                break
        return val[:63]
    if tool_name == "Agent":
        return str(tool_input.get("description", ""))[:63]
    return ""


def _sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in (
        "secret", "token", "password", "credential", "authorization", "api_key", "apikey"
    ))


def _redact_command(command: str) -> str:
    """Hide common inline credentials before showing a shell command on-device."""
    patterns = (
        r"(?i)(--?(?:api[-_]?key|token|password|secret|authorization)(?:=|\s+))(?:(\"[^\"]*\")|('[^']*')|([^\s]+))",
        r"(?i)\b((?:[A-Z0-9_]*API[_-]?KEY|[A-Z0-9_]*(?:ACCESS_)?TOKEN|[A-Z0-9_]*PASSWORD|[A-Z0-9_]*SECRET|[A-Z0-9_]*AUTHORIZATION)=)([^\s]+)",
        r"(https?://)[^/@\s:]+:[^/@\s]+@",
    )
    result = command
    result = re.sub(patterns[0], lambda m: m.group(1) + "[redacted]", result)
    result = re.sub(patterns[1], lambda m: m.group(1) + "[redacted]", result)
    result = re.sub(patterns[2], r"\1[redacted]@", result)
    return result


def main():
    if not os.path.exists(SOCKET_PATH):
        # Bridge not running — fall back to normal permission dialog
        sys.exit(1)

    try:
        hook_input = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        sys.exit(1)


    tool_name_raw = hook_input.get("tool_name", "Unknown")
    tool_input = hook_input.get("tool_input", {})

    # For tool_name like mcp__atlassian__searchJiraIssuesUsingJql, display as mcp_atlassian
    if "__" in tool_name_raw:
        parts = tool_name_raw.split("__")
        if len(parts) >= 2:
            tool_name = f"{parts[0]}_{parts[1]}"
        else:
            tool_name = tool_name_raw
    else:
        tool_name = tool_name_raw

    detail = extract_detail(tool_name_raw, tool_input)
    project = os.path.basename(str(hook_input.get("cwd", "")).rstrip("/\\"))
    if project:
        tool_name = f"{tool_name} @{project}"[:21]

    try:
        result = send_to_bridge(tool_name, detail, hook_input)
    except Exception:
        # Bridge error — fall back to normal permission dialog
        sys.exit(1)

    status = result.get("status")

    # Dismissed on Flipper — defer to Claude's normal permission dialog
    if status == "ask":
        # PermissionRequest accepts allow/deny only. Omit the decision to defer.
        print("{}")
        sys.exit(0)

    # Only act on explicit user decisions from Flipper
    if status != "ok":
        # no_flipper, timeout, error — fall back to normal dialog
        sys.exit(1)

    allowed = result.get("allowed", False)
    always = result.get("always", False)

    if allowed:
        decision = {"behavior": "allow"}
        if always:
            suggestions = hook_input.get("permission_suggestions", [])
            if suggestions:
                decision["updatedPermissions"] = suggestions
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PermissionRequest",
                "decision": decision,
            }
        }
    else:
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PermissionRequest",
                "decision": {"behavior": "deny", "message": "Denied on Flipper"},
            }
        }

    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    main()
