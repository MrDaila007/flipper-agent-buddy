"""Tests for correlated, serialized Claude permission prompts."""

import asyncio
import json

from bridge.daemon import Daemon


class FakeSerial:
    def __init__(self):
        self.connected = True
        self.sent = []

    async def send(self, payload):
        self.sent.append(json.loads(payload.decode().strip()))


def make_daemon():
    daemon = Daemon.__new__(Daemon)
    daemon.serial = FakeSerial()
    daemon._perm_lock = asyncio.Lock()
    daemon._perm_futures = {}
    daemon._active_perm_id = None
    return daemon


def test_permission_requests_queue_and_ignore_stale_replies():
    async def scenario():
        daemon = make_daemon()
        first = asyncio.create_task(
            daemon._permission_request("Bash", "echo first", "request-1", False)
        )
        await asyncio.sleep(0)
        second = asyncio.create_task(
            daemon._permission_request("Write", "/tmp/second", "request-2", True)
        )
        await asyncio.sleep(0)

        assert len(daemon.serial.sent) == 1
        assert daemon.serial.sent[0]["d"]["id"] == "request-1"

        await daemon._handle_flipper_msg({
            "t": "perm_resp", "d": {"id": "request-2", "allow": True}
        })
        assert not first.done()
        assert not second.done()

        await daemon._handle_flipper_msg({
            "t": "perm_resp", "d": {"id": "request-1", "allow": True}
        })
        assert await first == {"status": "ok", "allowed": True, "always": False}
        await asyncio.sleep(0)

        assert len(daemon.serial.sent) == 2
        assert daemon.serial.sent[1]["d"]["id"] == "request-2"
        assert daemon.serial.sent[1]["d"]["allow_always"] is True

        await daemon._handle_flipper_msg({
            "t": "perm_resp", "d": {"id": "request-1", "allow": False}
        })
        assert not second.done()
        await daemon._handle_flipper_msg({
            "t": "perm_resp", "d": {"id": "request-2", "allow": False}
        })
        assert await second == {"status": "ok", "allowed": False, "always": False}

    asyncio.run(scenario())
