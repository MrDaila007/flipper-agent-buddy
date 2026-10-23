"""Codex-specific hook adapter tests."""

import importlib.util
import io
import json
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from bridge.daemon import Daemon


SCRIPTS = Path(__file__).parents[2] / "scripts"


def load_script(name: str):
    path = SCRIPTS / name
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_permission_detail_for_apply_patch():
    hook = load_script("on-permission-request.py")
    assert hook.extract_detail("apply_patch", {"command": "*** Begin Patch"}) == "File change"


def test_post_tool_display_names():
    hook = load_script("on-post-tool-use.py")
    assert hook.display_name("apply_patch") == "Edit"
    assert hook.display_name("mcp__github__search") == "mcp_github"
    assert hook.display_name("Bash") == "Bash"


def test_post_tool_failure_shapes():
    hook = load_script("on-post-tool-use.py")
    assert hook.tool_failed({"tool_response": {"exit_code": 1}})
    assert hook.tool_failed({"tool_response": {"success": False}})
    assert hook.tool_failed({"tool_response": {"status": "failed"}})
    assert not hook.tool_failed({"tool_response": {"exit_code": 0}})


@pytest.mark.parametrize("response", [
    {"isError": True}, '{"exit_code": 2}', '{"isError": true}',
])
def test_current_tool_failures(response):
    assert load_script("on-post-tool-use.py").tool_failed({"tool_response": response})


@pytest.mark.parametrize("result, expected", [
    ({"status": "ask"}, {}),
    ({"status": "ok", "allowed": True, "always": True}, {"behavior": "allow"}),
    ({"status": "ok", "allowed": False}, {"behavior": "deny", "message": "Denied on Flipper"}),
])
def test_permission_decisions(monkeypatch, capsys, result, expected):
    hook = load_script("on-permission-request.py")
    monkeypatch.setattr(hook.os.path, "exists", lambda _: True)
    monkeypatch.setattr(hook.sys, "stdin", io.StringIO('{"tool_name":"Bash","tool_input":{"command":"ls"}}'))
    monkeypatch.setattr(hook, "send_to_bridge", lambda *_: result)
    with pytest.raises(SystemExit) as stopped:
        hook.main()
    assert stopped.value.code == 0
    output = json.loads(capsys.readouterr().out)
    if expected:
        assert output["hookSpecificOutput"]["decision"] == expected
    else:
        assert output == {}


@pytest.mark.parametrize("status", ["busy", "timeout", "no_flipper", "error"])
def test_permission_unavailable_defers(monkeypatch, capsys, status):
    hook = load_script("on-permission-request.py")
    monkeypatch.setattr(hook.os.path, "exists", lambda _: True)
    monkeypatch.setattr(hook.sys, "stdin", io.StringIO('{"tool_name":"Bash"}'))
    monkeypatch.setattr(hook, "send_to_bridge", lambda *_: {"status": status})
    with pytest.raises(SystemExit) as stopped:
        hook.main()
    assert stopped.value.code == 1
    assert not capsys.readouterr().out


@pytest.mark.asyncio
async def test_sessions_survive_compaction_and_close_independently(monkeypatch):
    daemon = Daemon(Mock(), dictation=Mock(), input_backend=Mock())
    daemon.serial.send = AsyncMock()
    monkeypatch.setattr(daemon, "_load_commands", lambda: [])
    for session, source in [("one", "startup"), ("one", "compact"), ("two", "fork")]:
        await daemon._handle_ipc_action({
            "action": "codex_connect", "session_id": session, "source": source,
            "session_key": session, "tty": "/dev/pts/1", "window_id": "123",
        })
    assert daemon._sessions == {"one", "two"}
    assert daemon._session_targets["one"]["window_id"] == "123"
    assert any(b"Forked session" in call.args[0] for call in daemon.serial.send.call_args_list)

    await daemon._handle_ipc_action({"action": "codex_disconnect", "session_id": "one", "shutdown": True})
    assert daemon._codex_connected
    assert not daemon._stop_requested.is_set()
    assert "one" not in daemon._session_targets
    await daemon._handle_ipc_action({"action": "codex_disconnect", "session_id": "two", "shutdown": True})
    assert not daemon._codex_connected
    assert daemon._stop_requested.is_set()
    assert not daemon._session_targets


def test_session_end_does_not_depend_on_terminal_detection(monkeypatch):
    hook = load_script("session-target.py")
    monkeypatch.setattr(hook.os.path, "exists", lambda _: True)
    monkeypatch.setattr(hook.sys, "stdin", io.StringIO('{"session_id":"thread-1"}'))
    monkeypatch.setattr(hook, "detect_tty", lambda: pytest.fail("SessionEnd must not scan processes"))
    send = Mock(return_value=0)
    monkeypatch.setattr(hook, "send_action", send)
    assert hook.main(["session-target.py", "end_session", "/tmp/test.sock"]) == 0
    send.assert_called_once_with("/tmp/test.sock", "codex_disconnect", {
        "session_key": "thread-1", "session_id": "thread-1", "shutdown": True,
    })


def test_interrupt_clears_turn_state_without_bridge(monkeypatch, tmp_path):
    hook = load_script("on-interrupt.py")
    paths = [tmp_path / name for name in ("stats", "skip")]
    for path in paths:
        path.touch()
    monkeypatch.setattr(hook, "STATE_FILES", paths)
    monkeypatch.setattr(hook, "SOCKET_PATH", str(tmp_path / "absent.sock"))
    hook.main()
    assert all(not path.exists() for path in paths)
