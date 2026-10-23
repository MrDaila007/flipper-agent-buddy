#!/usr/bin/env python3
"""SubagentStop hook: play distinct tone and show agent result snippet on Flipper."""

import json
import os
import socket
import sys

SOCKET_PATH = "/tmp/cursor-flipper-bridge.sock"


def send_to_flipper(sound: str, text: str, subtext: str = "") -> None:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(1.0)
    s.connect(SOCKET_PATH)
    msg = json.dumps({"action": "notify", "sound": sound, "vibro": False, "text": text, "subtext": subtext})
    s.sendall(msg.encode())
    s.shutdown(socket.SHUT_WR)
    s.recv(4096)
    s.close()


def main():
    if not os.path.exists(SOCKET_PATH):
        print("{}")
        return

    try:
        hook_input = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        print("{}")
        return

    agent_type = hook_input.get("subagent_type") or hook_input.get("agent_type") or "Agent"
    last_msg = (hook_input.get("summary") or hook_input.get("last_assistant_message") or "").strip()
    subtext = last_msg[:21] if last_msg else "stopped"

    try:
        # alert: single E5 blip + cyan flash, does NOT clear the working indicator
        status = hook_input.get("status", "completed")
        sound = {"error": "error", "aborted": "interrupt"}.get(status, "alert")
        send_to_flipper(sound, f"{agent_type} agent", subtext)
    except Exception:
        pass

    print("{}")


if __name__ == "__main__":
    main()
