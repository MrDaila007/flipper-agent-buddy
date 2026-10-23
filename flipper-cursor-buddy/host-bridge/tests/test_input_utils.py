"""Tests for pure utility functions in bridge/input.py."""

import pytest

from bridge.input import (
    _clean_target_value,
    _escape_applescript,
    _focus_script,
    _generic_focus_script,
    _key_code,
    InputTarget,
)


# ---------------------------------------------------------------------------
# _key_code
# ---------------------------------------------------------------------------

class TestKeyCode:
    def test_known_keys(self):
        assert _key_code("return") == 36
        assert _key_code("escape") == 53
        assert _key_code("down") == 125
        assert _key_code("space") == 49
        assert _key_code("tab") == 48
        assert _key_code("backspace") == 51
        assert _key_code("page_up") == 116
        assert _key_code("page_down") == 121

    def test_unknown_key_defaults_to_return(self):
        assert _key_code("nonexistent") == 36

    def test_empty_string_defaults_to_return(self):
        assert _key_code("") == 36


# ---------------------------------------------------------------------------
# _escape_applescript
# ---------------------------------------------------------------------------

class TestEscapeApplescript:
    def test_no_special_chars(self):
        assert _escape_applescript("hello") == "hello"

    def test_escapes_backslash(self):
        assert _escape_applescript("a\\b") == "a\\\\b"

    def test_escapes_double_quote(self):
        assert _escape_applescript('say "hi"') == 'say \\"hi\\"'

    def test_both_together(self):
        result = _escape_applescript('path\\"value')
        assert result == 'path\\\\\\"value'

    def test_empty_string(self):
        assert _escape_applescript("") == ""


# ---------------------------------------------------------------------------
# _clean_target_value
# ---------------------------------------------------------------------------

class TestCleanTargetValue:
    def test_none_returns_empty_string(self):
        assert _clean_target_value(None) == ""

    def test_strips_whitespace(self):
        assert _clean_target_value("  hello  ") == "hello"

    def test_int_converted_to_str(self):
        assert _clean_target_value(42) == "42"

    def test_already_clean_string(self):
        assert _clean_target_value("Terminal") == "Terminal"

    def test_empty_string(self):
        assert _clean_target_value("") == ""


# ---------------------------------------------------------------------------
# InputTarget.from_payload
# ---------------------------------------------------------------------------

class TestInputTargetFromPayload:
    def test_none_payload_returns_none(self):
        assert InputTarget.from_payload(None) is None

    def test_empty_dict_returns_none(self):
        assert InputTarget.from_payload({}) is None

    def test_all_empty_values_returns_none(self):
        payload = {
            "session_key": "",
            "app_name": "",
            "tty": None,
        }
        assert InputTarget.from_payload(payload) is None

    def test_app_name_only(self):
        t = InputTarget.from_payload({"app_name": "Terminal"})
        assert t is not None
        assert t.app_name == "Terminal"

    def test_tty_only(self):
        t = InputTarget.from_payload({"tty": "/dev/pts/3"})
        assert t is not None
        assert t.tty == "/dev/pts/3"

    def test_window_id_only(self):
        t = InputTarget.from_payload({"window_id": "0x12345"})
        assert t is not None
        assert t.window_id == "0x12345"

    def test_session_key_alone_is_not_enough(self):
        # session_key alone is not sufficient to identify a target
        t = InputTarget.from_payload({"session_key": "abc123"})
        assert t is None

    def test_full_payload(self):
        payload = {
            "session_key": "abc123",
            "app_name": "iTerm2",
            "term_program": "iTerm.app",
            "term_session_id": "sess-1",
            "iterm_session_id": "w0t0p0",
            "tty": "/dev/ttys001",
            "window_id": "",
        }
        t = InputTarget.from_payload(payload)
        assert t is not None
        assert t.session_key == "abc123"
        assert t.app_name == "iTerm2"
        assert t.tty == "/dev/ttys001"

    def test_values_are_stripped(self):
        t = InputTarget.from_payload({"app_name": "  Terminal  "})
        assert t.app_name == "Terminal"

    def test_none_values_become_empty_string(self):
        t = InputTarget.from_payload({"app_name": "Terminal", "tty": None})
        assert t.tty == ""


# ---------------------------------------------------------------------------
# InputTarget.describe
# ---------------------------------------------------------------------------

class TestInputTargetDescribe:
    def test_empty_target_returns_default(self):
        t = InputTarget()
        assert t.describe() == "default"

    def test_app_name_shown(self):
        t = InputTarget(app_name="Terminal")
        assert "app=Terminal" in t.describe()

    def test_tty_shown(self):
        t = InputTarget(tty="/dev/pts/1")
        assert "tty=/dev/pts/1" in t.describe()

    def test_window_id_shown(self):
        t = InputTarget(window_id="0xabc")
        assert "window_id=0xabc" in t.describe()

    def test_multiple_parts_joined_with_comma(self):
        t = InputTarget(app_name="Terminal", tty="/dev/pts/1")
        desc = t.describe()
        assert "app=Terminal" in desc
        assert "tty=/dev/pts/1" in desc
        assert ", " in desc


# ---------------------------------------------------------------------------
# _generic_focus_script
# ---------------------------------------------------------------------------

class TestGenericFocusScript:
    def test_contains_app_name(self):
        script = _generic_focus_script("Terminal")
        assert '"Terminal"' in script

    def test_escapes_quotes_in_app_name(self):
        script = _generic_focus_script('My"App')
        assert '\\"' in script
        assert '"My"App"' not in script

    def test_activates_application(self):
        script = _generic_focus_script("iTerm2")
        assert "activate" in script


# ---------------------------------------------------------------------------
# _focus_script
# ---------------------------------------------------------------------------

class TestFocusScript:
    def test_none_target_returns_empty(self):
        assert _focus_script(None) == ""

    def test_no_app_name_returns_empty(self):
        t = InputTarget(tty="/dev/pts/1")  # no app_name
        assert _focus_script(t) == ""

    def test_generic_app(self):
        t = InputTarget(app_name="Visual Studio Code")
        script = _focus_script(t)
        assert "Visual Studio Code" in script
        assert "activate" in script

    def test_terminal_app_uses_terminal_focus(self):
        t = InputTarget(app_name="Terminal", tty="/dev/ttys001")
        script = _focus_script(t)
        # should reference the tty
        assert "/dev/ttys001" in script

    def test_terminal_without_tty_uses_generic_focus(self):
        t = InputTarget(app_name="Terminal")
        script = _focus_script(t)
        # no tty matching, falls back to generic activate
        assert "activate" in script
