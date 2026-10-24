#!/usr/bin/env python3
"""Enable, disable, or inspect the Codex bridge state."""

from __future__ import annotations

import json
import hashlib
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path


RUNTIME_DIR = Path(os.environ.get("FLIPPER_RUNTIME_DIR") or (
    Path(os.environ["XDG_RUNTIME_DIR"]) / "flipper-codex-buddy"
    if os.environ.get("XDG_RUNTIME_DIR") else f"/tmp/flipper-codex-buddy-{os.getuid()}"
))
SOCKET = os.environ.get("FLIPPER_BRIDGE_SOCKET", str(RUNTIME_DIR / "bridge.sock"))
PIDFILE = os.environ.get("FLIPPER_BRIDGE_PIDFILE", str(RUNTIME_DIR / "bridge.pid"))
LOG = os.environ.get("FLIPPER_BRIDGE_LOG", str(RUNTIME_DIR / "bridge.log"))


def _plugin_root() -> Path:
    return Path(os.environ.get("PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT") or ".")


def _plugin_data() -> Path:
    return Path(
        os.environ.get("PLUGIN_DATA")
        or os.environ.get("CLAUDE_PLUGIN_DATA")
        or "/tmp/flipper-codex-buddy"
    )


def _bridge_dir() -> Path:
    return _plugin_root() / "host-bridge"


def _state_file() -> Path:
    override = os.environ.get("FLIPPER_BRIDGE_ENABLED_FILE")
    if override:
        return Path(override)
    return _plugin_data() / "bridge-enabled"


def _read_enabled() -> bool:
    path = _state_file()
    try:
        raw = path.read_text(encoding="utf-8").strip().lower()
    except Exception:
        return True
    if raw in {"0", "false", "off", "disabled", "no"}:
        return False
    if raw in {"1", "true", "on", "enabled", "yes"}:
        return True
    return True


def _write_enabled(enabled: bool) -> None:
    path = _state_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("1\n" if enabled else "0\n", encoding="utf-8")


def _socket_alive() -> bool:
    if not Path(SOCKET).is_socket():
        return False
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(1.0)
            client.connect(SOCKET)
            client.sendall(b"{}")
            client.shutdown(socket.SHUT_WR)
            client.recv(1024)
        return True
    except Exception:
        return False


def _read_pid() -> int | None:
    try:
        pid = int(Path(PIDFILE).read_text(encoding="utf-8").strip())
        return pid if pid > 0 else None
    except Exception:
        return None


def _ensure_venv() -> Path:
    data_dir = _plugin_data()
    venv_dir = data_dir / "venv"
    marker = venv_dir / ".installed-hash"
    bridge_dir = _bridge_dir()
    digest = hashlib.md5()
    for path in [bridge_dir / "pyproject.toml", *sorted((bridge_dir / "bridge").glob("*.py"))]:
        try:
            digest.update(path.read_bytes())
        except Exception:
            continue
    current_hash = digest.hexdigest()
    if not venv_dir.is_dir() or not marker.is_file() or marker.read_text(encoding="utf-8").strip() != current_hash:
        data_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
        subprocess.run(
            [str(venv_dir / "bin" / "pip"), "install", "-q", "--force-reinstall", str(bridge_dir)],
            check=True,
        )
        marker.write_text(current_hash + "\n", encoding="utf-8")
    return venv_dir


def _start_bridge() -> int:
    _ensure_runtime_dir()
    venv_dir = _ensure_venv()
    old_umask = os.umask(0o077)
    try:
        log_file = open(LOG, "a", encoding="utf-8")
    finally:
        os.umask(old_umask)
    os.chmod(LOG, 0o600)
    proc = subprocess.Popen(
        [str(venv_dir / "bin" / "python"), "-m", "bridge"],
        stdout=log_file,
        stderr=subprocess.STDOUT,
        close_fds=True,
    )
    Path(PIDFILE).write_text(f"{proc.pid}\n", encoding="utf-8")
    return proc.pid


def _ensure_runtime_dir() -> None:
    RUNTIME_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = RUNTIME_DIR.lstat()
    if (not RUNTIME_DIR.is_dir() or RUNTIME_DIR.is_symlink()
            or info.st_uid != os.getuid() or info.st_mode & 0o077):
        raise RuntimeError(f"Runtime directory must be private and user-owned: {RUNTIME_DIR}")


def _stop_bridge() -> bool:
    pid = _read_pid()
    if pid is None:
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    except Exception:
        return False
    for _ in range(50):
        if not Path(SOCKET).exists():
            break
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        except Exception:
            pass
        time.sleep(0.1)
    try:
        Path(PIDFILE).unlink(missing_ok=True)
    except Exception:
        pass
    return True


def _send_action(action: str) -> dict[str, object] | None:
    if not Path(SOCKET).exists():
        return None
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(3.0)
            client.connect(SOCKET)
            client.sendall(json.dumps({"action": action}).encode("utf-8"))
            client.shutdown(socket.SHUT_WR)
            payload = client.recv(65536).decode("utf-8", "replace").strip()
            return json.loads(payload) if payload else {}
    except Exception:
        return None


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in {"enable", "disable", "toggle", "status"}:
        print("usage: bridge-control.py <enable|disable|toggle|status>", file=sys.stderr)
        return 2

    action = argv[1]
    enabled = _read_enabled()

    if action == "status":
        running = _socket_alive()
        print(json.dumps({"enabled": enabled, "running": running, "pid": _read_pid()}))
        return 0

    if action == "toggle":
        action = "disable" if enabled else "enable"

    if action == "disable":
        _write_enabled(False)
        if _socket_alive():
            response = _send_action("shutdown")
            if response is None:
                _stop_bridge()
            else:
                for _ in range(50):
                    if not Path(SOCKET).exists():
                        break
                    time.sleep(0.1)
                _stop_bridge()
            return 0
        _stop_bridge()
        return 0

    _write_enabled(True)
    if _socket_alive():
        _send_action("bridge_enable")
        return 0

    try:
        _start_bridge()
    except Exception as exc:
        print(f"failed to start bridge: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
