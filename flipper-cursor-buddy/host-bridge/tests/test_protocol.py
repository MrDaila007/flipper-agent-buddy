"""Tests for bridge/protocol.py — JSON codec and message builders."""

import json
import pytest

from bridge import protocol


# ---------------------------------------------------------------------------
# encode / decode
# ---------------------------------------------------------------------------

class TestEncode:
    def test_returns_bytes(self):
        result = protocol.encode("ping")
        assert isinstance(result, bytes)

    def test_ends_with_newline(self):
        result = protocol.encode("ping")
        assert result.endswith(b"\n")

    def test_structure(self):
        msg = json.loads(protocol.encode("ping"))
        assert msg["v"] == 1
        assert msg["t"] == "ping"
        assert msg["d"] == {}

    def test_with_data(self):
        msg = json.loads(protocol.encode("notify", {"sound": "success"}))
        assert msg["t"] == "notify"
        assert msg["d"]["sound"] == "success"

    def test_none_data_becomes_empty_dict(self):
        msg = json.loads(protocol.encode("ping", None))
        assert msg["d"] == {}

    def test_no_spaces_in_json(self):
        # separators=(",", ":") — no spaces, saves bytes on the wire
        raw = protocol.encode("ping").rstrip(b"\n")
        assert b" " not in raw


class TestDecode:
    def test_valid_message(self):
        line = b'{"v":1,"t":"hello","d":{"bt":"Flipper"}}\n'
        msg = protocol.decode(line)
        assert msg is not None
        assert msg["t"] == "hello"
        assert msg["d"]["bt"] == "Flipper"

    def test_strips_whitespace(self):
        line = b'  {"v":1,"t":"pong","d":{}}\n  '
        msg = protocol.decode(line)
        assert msg is not None
        assert msg["t"] == "pong"

    def test_empty_bytes_returns_none(self):
        assert protocol.decode(b"") is None
        assert protocol.decode(b"   \n") is None

    def test_invalid_json_returns_none(self):
        assert protocol.decode(b"{broken json}") is None

    def test_missing_t_field_returns_none(self):
        assert protocol.decode(b'{"v":1,"d":{}}') is None

    def test_roundtrip(self):
        original = protocol.encode("state", {"claude": True})
        decoded = protocol.decode(original)
        assert decoded["t"] == "state"
        assert decoded["d"]["claude"] is True

    def test_concatenated_messages(self):
        line = (
            b'>: {"v":1,"t":"ping","d":{}}'
            b'{"v":1,"t":"hello","d":{"fw":"0.1.0","bt":"Flipper"}}\n'
        )
        msgs = protocol.decode_all(line)
        assert [m["t"] for m in msgs] == ["ping", "hello"]
        assert msgs[1]["d"]["bt"] == "Flipper"


# ---------------------------------------------------------------------------
# make_id
# ---------------------------------------------------------------------------

class TestMakeId:
    def test_length(self):
        assert len(protocol.make_id()) == 8

    def test_hex_characters(self):
        id_ = protocol.make_id()
        assert all(c in "0123456789abcdef" for c in id_)

    def test_uniqueness(self):
        ids = {protocol.make_id() for _ in range(100)}
        assert len(ids) == 100


# ---------------------------------------------------------------------------
# notify_msg
# ---------------------------------------------------------------------------

class TestNotifyMsg:
    def test_basic(self):
        msg = json.loads(protocol.notify_msg("success"))
        assert msg["t"] == "notify"
        assert msg["d"]["sound"] == "success"
        assert msg["d"]["vibro"] is True
        assert msg["d"]["text"] == ""

    def test_vibro_false(self):
        msg = json.loads(protocol.notify_msg("alert", vibro=False))
        assert msg["d"]["vibro"] is False

    def test_text_and_subtext(self):
        msg = json.loads(protocol.notify_msg("success", text="Done", subtext="2 files"))
        assert msg["d"]["text"] == "Done"
        assert msg["d"]["sub"] == "2 files"

    def test_subtext_truncated_to_21(self):
        long = "a" * 30
        msg = json.loads(protocol.notify_msg("success", subtext=long))
        assert len(msg["d"]["sub"]) == 21

    def test_no_subtext_key_when_empty(self):
        msg = json.loads(protocol.notify_msg("success", subtext=""))
        assert "sub" not in msg["d"]


# ---------------------------------------------------------------------------
# state_msg
# ---------------------------------------------------------------------------

class TestStateMsg:
    def test_connected_true(self):
        msg = json.loads(protocol.state_msg(True))
        assert msg["t"] == "state"
        assert msg["d"]["claude"] is True
        assert msg["d"]["host"] == "cursor"

    def test_connected_false(self):
        msg = json.loads(protocol.state_msg(False))
        assert msg["d"]["claude"] is False
        assert msg["d"]["host"] == "cursor"

    def test_default_is_false(self):
        msg = json.loads(protocol.state_msg())
        assert msg["d"]["claude"] is False
        assert msg["d"]["host"] == "cursor"

    def test_custom_host(self):
        msg = json.loads(protocol.state_msg(True, host="claude"))
        assert msg["d"]["host"] == "claude"


# ---------------------------------------------------------------------------
# status_msg
# ---------------------------------------------------------------------------

class TestStatusMsg:
    def test_line1(self):
        msg = json.loads(protocol.status_msg("Running tests"))
        assert msg["t"] == "status"
        assert msg["d"]["line1"] == "Running tests"

    def test_line1_truncated_to_21(self):
        msg = json.loads(protocol.status_msg("a" * 30))
        assert len(msg["d"]["line1"]) == 21

    def test_line2_included_when_present(self):
        msg = json.loads(protocol.status_msg("L1", "L2"))
        assert msg["d"]["line2"] == "L2"

    def test_line2_truncated_to_21(self):
        msg = json.loads(protocol.status_msg("L1", "b" * 30))
        assert len(msg["d"]["line2"]) == 21

    def test_no_line2_key_when_empty(self):
        msg = json.loads(protocol.status_msg("L1", ""))
        assert "line2" not in msg["d"]


class TestUsageMsg:
    def test_basic(self):
        msg = json.loads(protocol.usage_msg(context_pct=82, session_pct=45, compact_level=2))
        assert msg["t"] == "usage"
        assert msg["d"]["ctx"] == 82
        assert msg["d"]["sess"] == 45
        assert msg["d"]["clvl"] == 2


# ---------------------------------------------------------------------------
# ping_msg
# ---------------------------------------------------------------------------

class TestPingMsg:
    def test_no_rssi(self):
        msg = json.loads(protocol.ping_msg())
        assert msg["t"] == "ping"
        assert msg["d"] == {}

    def test_with_rssi(self):
        msg = json.loads(protocol.ping_msg(rssi=-72))
        assert msg["d"]["rssi"] == -72

    def test_rssi_converted_to_int(self):
        msg = json.loads(protocol.ping_msg(rssi=-65.7))
        assert isinstance(msg["d"]["rssi"], int)
        assert msg["d"]["rssi"] == -65


# ---------------------------------------------------------------------------
# menu_msg
# ---------------------------------------------------------------------------

class TestMenuMsg:
    def test_items_joined_by_pipe(self):
        msg = json.loads(protocol.menu_msg(["/commit", "/review", "/build"]))
        assert msg["t"] == "menu"
        assert msg["d"]["items"] == "/commit|/review|/build"

    def test_empty_list(self):
        msg = json.loads(protocol.menu_msg([]))
        assert msg["d"]["items"] == ""

    def test_single_item(self):
        msg = json.loads(protocol.menu_msg(["/help"]))
        assert msg["d"]["items"] == "/help"


# ---------------------------------------------------------------------------
# perm_msg
# ---------------------------------------------------------------------------

class TestPermMsg:
    def test_tool_only(self):
        msg = json.loads(protocol.perm_msg("Bash"))
        assert msg["t"] == "perm"
        assert msg["d"]["tool"] == "Bash"

    def test_tool_truncated_to_21(self):
        msg = json.loads(protocol.perm_msg("T" * 30))
        assert len(msg["d"]["tool"]) == 21

    def test_detail_included(self):
        msg = json.loads(protocol.perm_msg("Edit", "modify auth.py"))
        assert msg["d"]["detail"] == "modify auth.py"

    def test_detail_truncated_to_21(self):
        msg = json.loads(protocol.perm_msg("Edit", "x" * 30))
        assert len(msg["d"]["detail"]) == 21

    def test_no_detail_key_when_empty(self):
        msg = json.loads(protocol.perm_msg("Bash", ""))
        assert "detail" not in msg["d"]
