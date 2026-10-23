"""Cursor-specific hook adapter tests."""

import importlib.util
import io
import json
from pathlib import Path
from unittest.mock import Mock

import pytest


SCRIPTS = Path(__file__).parents[2] / "scripts"


def load_script(name: str):
    path = SCRIPTS / name
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_permission_detail_for_shell():
    hook = load_script("on-permission-request.py")
    assert hook.extract_detail("Shell", {"command": "ls -la"}) == "ls -la"


def test_permission_detail_for_mcp():
    hook = load_script("on-permission-request.py")
    assert hook.extract_detail("MCP: context7", {}) == "context7"


def test_post_tool_display_names():
    hook = load_script("on-post-tool-use.py")
    assert hook.display_name("Shell") == "Shell"
    assert hook.display_name("MCP: github") == "MCP"


def test_post_tool_sound_mapping():
    hook = load_script("on-post-tool-use.py")
    assert hook.sound_for_tool("Shell") == "cmd"
    assert hook.sound_for_tool("Write") == "enter"
    assert hook.sound_for_tool("Task") is None


@pytest.mark.parametrize("available", [False, True])
def test_subagent_start_always_returns_permission(monkeypatch, capsys, available):
    hook = load_script("on-subagent-start.py")
    monkeypatch.setattr(hook.os.path, "exists", lambda _: available)
    monkeypatch.setattr(hook.sys, "stdin", io.StringIO('{"subagent_type":"explore"}'))
    display = Mock()
    monkeypatch.setattr(hook, "send_display", display)
    hook.main()
    assert json.loads(capsys.readouterr().out) == {"permission": "allow"}
    if available:
        display.assert_called_once_with("explore agent", "started")


def test_subagent_start_bridge_error_does_not_block(monkeypatch, capsys):
    hook = load_script("on-subagent-start.py")
    monkeypatch.setattr(hook.os.path, "exists", lambda _: True)
    monkeypatch.setattr(hook.sys, "stdin", io.StringIO('{}'))
    monkeypatch.setattr(hook, "send_display", Mock(side_effect=OSError))
    hook.main()
    assert json.loads(capsys.readouterr().out) == {"permission": "allow"}


@pytest.mark.parametrize("status,sound", [("completed", "alert"), ("error", "error"), ("aborted", "interrupt")])
def test_current_subagent_stop_payload(monkeypatch, capsys, status, sound):
    hook = load_script("on-subagent-stop.py")
    monkeypatch.setattr(hook.os.path, "exists", lambda _: True)
    payload = {"subagent_type": "shell", "summary": "Tests passed", "status": status}
    monkeypatch.setattr(hook.sys, "stdin", io.StringIO(json.dumps(payload)))
    notify = Mock()
    monkeypatch.setattr(hook, "send_to_flipper", notify)
    hook.main()
    notify.assert_called_once_with(sound, "shell agent", "Tests passed")
    assert json.loads(capsys.readouterr().out) == {}


@pytest.mark.parametrize("status", ["ask", "busy", "timeout", "no_flipper"])
def test_permission_fallback_does_not_emit_unsupported_ask(monkeypatch, capsys, status):
    hook = load_script("on-permission-request.py")
    monkeypatch.setattr(hook.os.path, "exists", lambda _: True)
    monkeypatch.setattr(hook.sys, "stdin", io.StringIO('{"tool_name":"Shell"}'))
    monkeypatch.setattr(hook, "send_to_bridge", lambda *_: {"status": status})
    with pytest.raises(SystemExit) as stopped:
        hook.main()
    assert stopped.value.code == 1
    assert not capsys.readouterr().out
