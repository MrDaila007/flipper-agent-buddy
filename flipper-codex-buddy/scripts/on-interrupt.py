#!/usr/bin/env python3
"""Interrupt hook: clear per-turn state and report cancellation promptly."""

import json
import os
from pathlib import Path
import socket
from runtime_paths import runtime_path, socket_path

SOCKET_PATH = socket_path()
STATE_FILES = (
    runtime_path("turn-stats.json"),
    runtime_path("skip-stop.flag"),
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
