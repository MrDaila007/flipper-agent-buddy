#!/usr/bin/env python3
"""Interrupt hook: clear per-turn state and report cancellation promptly."""

import json
import os
from pathlib import Path
import socket

SOCKET_PATH = os.environ.get("FLIPPER_BRIDGE_SOCKET", "/tmp/codex-flipper-bridge.sock")
STATE_FILES = (
    "/tmp/codex-flipper-turn-stats.json",
    "/tmp/codex-flipper-skip-stop.flag",
)


def main():
    for name in STATE_FILES:
        try:
            Path(name).unlink(missing_ok=True)
        except OSError:
            pass
    payload = {"action": "notify", "sound": "interrupt", "vibro": True,
               "text": "Interrupted", "subtext": ""}
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(0.5)
            client.connect(SOCKET_PATH)
            client.sendall(json.dumps(payload).encode())
            client.shutdown(socket.SHUT_WR)
            client.recv(4096)
    except OSError:
        pass


if __name__ == "__main__":
    main()
