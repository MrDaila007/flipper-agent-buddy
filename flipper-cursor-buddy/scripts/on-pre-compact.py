#!/usr/bin/env python3
"""PreCompact hook: compaction LED + context-aware character animation."""

import json
import os
import socket
import sys

SOCKET_PATH = "/tmp/cursor-flipper-bridge.sock"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PENDING_COMPACT_FLAG = "/tmp/cursor-flipper-pending-compact.flag"


def send_to_flipper(sound: str, vibro: bool, text: str, subtext: str = "") -> None:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(1.0)
    s.connect(SOCKET_PATH)
    msg = json.dumps({"action": "notify", "sound": sound, "vibro": vibro, "text": text, "subtext": subtext})
    s.sendall(msg.encode())
    s.shutdown(socket.SHUT_WR)
    s.recv(4096)
    s.close()


def main():
    if not os.path.exists(SOCKET_PATH):
        sys.exit(0)

    payload = sys.stdin.read()
    try:
        send_to_flipper("led_compact", False, "Compacting...")
        try:
            open(PENDING_COMPACT_FLAG, "w").close()
        except Exception:
            pass
        if payload.strip():
            proc = os.popen(f"python3 {SCRIPT_DIR}/context_usage.py pre_compact", "w")
            proc.write(payload)
            proc.close()
    except Exception:
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
