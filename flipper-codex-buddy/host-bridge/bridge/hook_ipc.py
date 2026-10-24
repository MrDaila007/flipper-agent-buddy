"""Unix domain socket server for Codex hooks IPC.

Simple request/response: hooks connect, send a JSON action, get a response.
"""

import asyncio
import json
import logging
import os
import socket
import stat
import struct
from pathlib import Path

from . import config

log = logging.getLogger(__name__)


class HookIPC:
    MAX_REQUEST_BYTES = 64 * 1024

    def __init__(self):
        self._server: asyncio.Server | None = None
        self._on_action = None
        self._socket_identity = None

    def on_action(self, callback):
        self._on_action = callback

    async def start(self):
        path = Path(config.SOCKET_PATH)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        parent = path.parent.lstat()
        if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.getuid()
                or stat.S_IMODE(parent.st_mode) & 0o077):
            raise RuntimeError(f"IPC directory must be owned by this user and private: {path.parent}")
        try:
            existing = path.lstat()
        except FileNotFoundError:
            existing = None
        if existing:
            if not stat.S_ISSOCK(existing.st_mode) or existing.st_uid != os.getuid():
                raise RuntimeError(f"Refusing to replace non-owned IPC path: {path}")
            probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            probe.settimeout(0.2)
            try:
                probe.connect(str(path))
            except (ConnectionRefusedError, FileNotFoundError):
                pass
            else:
                raise RuntimeError(f"Another bridge daemon already owns {path}")
            finally:
                probe.close()
            path.unlink()
        self._server = await asyncio.start_unix_server(
            self._handle_client, path=str(path)
        )
        os.chmod(path, 0o600)
        bound = path.lstat()
        self._socket_identity = (bound.st_dev, bound.st_ino)
        log.info("IPC listening on %s", config.SOCKET_PATH)

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ):
        try:
            peer = writer.get_extra_info("socket")
            if peer is not None and hasattr(socket, "SO_PEERCRED"):
                credentials = peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
                _pid, uid, _gid = struct.unpack("3i", credentials)
                if uid != os.getuid():
                    log.warning("IPC: rejected peer uid=%d", uid)
                    return

            chunks = []
            total = 0
            async with asyncio.timeout(5.0):
                while True:
                    chunk = await reader.read(min(4096, self.MAX_REQUEST_BYTES + 1 - total))
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > self.MAX_REQUEST_BYTES:
                        raise ValueError("IPC request too large")
                    chunks.append(chunk)
            data = b"".join(chunks)
            if not data:
                return

            request = json.loads(data.decode().strip())
            if not isinstance(request, dict) or not isinstance(request.get("action"), str):
                raise ValueError("IPC request must be an object with a string action")

            if self._on_action:
                response = await self._on_action(request)
            else:
                response = {"status": "ok"}

            writer.write(json.dumps(response).encode() + b"\n")
            await writer.drain()
        except (asyncio.TimeoutError, TimeoutError):
            log.warning("IPC: read timeout")
        except (ConnectionError, BrokenPipeError):
            log.debug("IPC: client disconnected")
        except Exception as e:
            log.error("IPC: error: %s", e)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def stop(self):
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        try:
            path = Path(config.SOCKET_PATH)
            current = path.lstat()
            identity = (current.st_dev, current.st_ino)
            if (stat.S_ISSOCK(current.st_mode) and current.st_uid == os.getuid()
                    and identity == self._socket_identity):
                path.unlink()
        except FileNotFoundError:
            pass
        self._socket_identity = None
