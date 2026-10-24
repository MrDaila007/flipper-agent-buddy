"""Private per-user runtime paths shared by the daemon hooks."""

from __future__ import annotations

import os
from pathlib import Path


def runtime_dir() -> Path:
    explicit = os.environ.get("FLIPPER_RUNTIME_DIR")
    if explicit:
        return Path(explicit)
    xdg = os.environ.get("XDG_RUNTIME_DIR")
    if xdg:
        return Path(xdg) / "flipper-codex-buddy"
    return Path(f"/tmp/flipper-codex-buddy-{os.getuid()}")


def runtime_path(name: str) -> Path:
    return runtime_dir() / name


def socket_path() -> str:
    return os.environ.get("FLIPPER_BRIDGE_SOCKET", str(runtime_path("bridge.sock")))
