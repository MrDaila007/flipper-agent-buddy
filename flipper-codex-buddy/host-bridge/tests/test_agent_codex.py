"""Real Unix WebSocket contract tests; no model calls or GUI automation."""

import asyncio
import json
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio
from websockets.asyncio.server import unix_serve

from bridge.agent import AgentError
from bridge.agent_codex import CodexAppServer
from bridge.agent_control import AgentControl
from bridge.daemon import Daemon
from bridge import config


class AppServer:
    def __init__(self):
        self.calls = []
        self.clients = set()
        self.requests = {}
        self.answers = []
        self.resolve_answers = True
        self.subscribed = asyncio.Event()
        self.threads = {
            "a": {"id": "a", "name": "First agent", "cwd": "/project/a", "status": {"type": "active"}},
            "b": {"id": "b", "name": "Second agent", "cwd": "/project/b", "status": {"type": "idle"}},
        }
        self.turns = {
            "a": [{"id": "turn-a", "status": "inProgress"}],
            "b": [{"id": "turn-b", "status": "completed"}],
        }
        self.interrupt_received = asyncio.Event()
        self.confirm = True
        self.fail_method = None
        self.drop_method = None
        self.hang_method = None

    async def send_request(self, request_id, thread_id="a", method="item/commandExecution/requestApproval", **params):
        message = {"id": request_id, "method": method, "params": {
            "threadId": thread_id, "turnId": "turn-" + thread_id,
            "itemId": "item-" + str(request_id), "command": "echo test", **params,
        }}
        self.requests[request_id] = message
        for ws in list(self.clients):
            await ws.send(json.dumps(message))

    async def resolve(self, request_id):
        request = self.requests.pop(request_id)
        for ws in list(self.clients):
            await ws.send(json.dumps({"method": "serverRequest/resolved", "params": {
                "threadId": request["params"]["threadId"], "requestId": request_id,
            }}))

    async def handle(self, ws):
        self.clients.add(ws)
        try:
            await self._handle(ws)
        finally:
            self.clients.discard(ws)

    async def _handle(self, ws):
        initialized = False
        async for raw in ws:
            message = json.loads(raw)
            method, params = message.get("method"), message.get("params", {})
            if method is None:
                self.answers.append(message)
                if self.resolve_answers:
                    await self.resolve(message["id"])
                continue
            self.calls.append((method, params))
            if method == "initialized":
                initialized = True
                continue
            assert method == "initialize" or initialized
            if method == self.drop_method:
                await ws.close()
                return
            if method == self.hang_method:
                continue
            if method == self.fail_method:
                await ws.send(json.dumps({"id": message["id"], "error": {"code": -1, "message": "denied"}}))
                continue
            if method == "initialize":
                result = {"userAgent": "test"}
            elif method == "thread/loaded/list":
                result = {"data": list(self.threads), "nextCursor": None}
            elif method == "thread/read":
                result = {"thread": self.threads[params["threadId"]]}
            elif method == "thread/turns/list":
                result = {"data": self.turns[params["threadId"]]}
            elif method == "thread/resume":
                result = {"thread": self.threads[params["threadId"]]}
                self.subscribed.set()
                for request in self.requests.values():
                    if request["params"]["threadId"] == params["threadId"]:
                        await ws.send(json.dumps(request))
            elif method == "turn/interrupt":
                self.interrupt_received.set()
                if self.confirm:
                    for turn in self.turns[params["threadId"]]:
                        if turn["id"] == params["turnId"]:
                            turn["status"] = "interrupted"
                result = {}
            elif method == "skills/list":
                result = {"data": []}
            elif method == "account/rateLimits/read":
                result = {}
            elif method == "thread/compact/start":
                result = {}
            else:
                pytest.fail(f"Unexpected method: {method}")
            # Notifications must not be confused with command results.
            await ws.send(json.dumps({"method": "thread/status/changed", "params": {}}))
            await ws.send(json.dumps({"id": message["id"], "result": result}))


@pytest_asyncio.fixture
async def app_server(tmp_path):
    server = AppServer()
    path = str(tmp_path / "s")
    async with unix_serve(server.handle, path):
        client = CodexAppServer(path, timeout=.5, confirm_timeout=.2)
        try:
            yield server, client
        finally:
            await client.close()


@pytest.mark.asyncio
async def test_explicit_selection_and_observation_do_not_resume_threads(app_server):
    server, client = app_server
    assert [s.id for s in await client.list_sessions()] == ["a", "b"]
    assert client.selected_id is None
    with pytest.raises(AgentError, match="Select a session"):
        await client.interrupt()
    state = await client.select_session("a")
    assert state.turn_id == "turn-a"
    assert state.turn_status == "inProgress"
    assert (await client.get_state()).session.id == "a"
    assert not any(m in {"thread/resume", "thread/start", "turn/start"} for m, _ in server.calls)


@pytest.mark.asyncio
async def test_interrupt_targets_selected_thread_and_confirms_exact_turn(app_server):
    server, client = app_server
    await client.select_session("a")
    state = await client.interrupt()
    assert state.turn_status == "interrupted"
    assert [(m, p) for m, p in server.calls if m == "turn/interrupt"] == [
        ("turn/interrupt", {"threadId": "a", "turnId": "turn-a"}),
    ]
    assert server.turns["b"][0]["status"] == "completed"


@pytest.mark.asyncio
async def test_rpc_ack_is_not_confirmation(app_server):
    server, client = app_server
    server.confirm = False
    await client.select_session("a")
    with pytest.raises(AgentError, match="outcome not confirmed"):
        await client.interrupt()
    assert len([m for m, _ in server.calls if m == "turn/interrupt"]) == 1


@pytest.mark.asyncio
async def test_selection_change_and_new_turn_do_not_redirect_interrupt(app_server):
    server, client = app_server
    client.confirm_timeout = 1
    server.confirm = False
    await client.select_session("a")
    stopping = asyncio.create_task(client.interrupt())
    await server.interrupt_received.wait()
    await client.select_session("b")
    server.turns["a"].insert(0, {"id": "replacement", "status": "inProgress"})
    server.turns["a"][1]["status"] = "interrupted"
    result = await stopping
    assert result.session.id == "a"
    assert result.turn_id == "turn-a"
    assert client.selected_id == "b"
    assert len([m for m, _ in server.calls if m == "turn/interrupt"]) == 1


@pytest.mark.asyncio
async def test_unloaded_or_idle_target_cannot_interrupt(app_server):
    server, client = app_server
    await client.select_session("b")
    with pytest.raises(AgentError, match="no running turn"):
        await client.interrupt()
    del server.threads["b"]
    with pytest.raises(AgentError, match="no longer loaded"):
        await client.interrupt()
    with pytest.raises(AgentError):
        await client.select_session("missing")
    assert client.selected_id == "b"
    assert not any(m == "turn/interrupt" for m, _ in server.calls)


@pytest.mark.asyncio
async def test_empty_desktop_tab_can_be_selected_without_turn_history(app_server):
    server, client = app_server
    server.fail_method = "thread/turns/list"
    state = await client.select_session("b")
    assert state.session.status == "idle"
    assert state.turn_id is None
    assert client.selected_id == "b"
    assert not any(m == "thread/turns/list" for m, _ in server.calls)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["drop_method", "hang_method", "fail_method"])
async def test_failed_mutation_never_replays_and_reads_can_reconnect(app_server, failure):
    server, client = app_server
    await client.select_session("a")
    setattr(server, failure, "turn/interrupt")
    with pytest.raises(AgentError):
        await client.interrupt()
    assert len([m for m, _ in server.calls if m == "turn/interrupt"]) == 1
    setattr(server, failure, None)
    assert (await client.get_state()).session.id == "a"
    assert len([m for m, _ in server.calls if m == "turn/interrupt"]) == 1


@pytest.mark.asyncio
async def test_native_buttons_never_call_keyboard_and_hooks_cannot_change_target(app_server):
    server, client = app_server
    keyboard = Mock()
    daemon = Daemon(Mock(), dictation=Mock(), input_backend=keyboard, agent_backend=client)
    send = AsyncMock()
    daemon.serial.send = send
    daemon.agent_control.send = send
    response = await daemon._handle_ipc_action({"action": "agent_sessions"})
    assert response["status"] == "ok"
    assert len(response["sessions"]) == 2
    await daemon._handle_ipc_action({"action": "agent_select", "session_id": "a"})
    assert client.selected_id == "a"
    await daemon._handle_ipc_action({"action": "codex_connect", "session_id": "b", "window_id": "123"})
    assert client.selected_id == "a"
    assert await daemon._handle_ipc_action({"action": "permission_request"}) == {"status": "ask"}
    for kind in ["yes", "voice", "pgup", "ctrl_o", "backspace", "perm_resp", "space_down"]:
        await daemon._handle_flipper_msg({"t": kind})
        await asyncio.gather(*daemon.agent_control._tasks)
    await daemon._handle_flipper_msg({"t": "interrupt"})
    await asyncio.gather(*daemon.agent_control._tasks)
    keyboard.assert_not_called()
    assert not keyboard.mock_calls
    assert not any(m == "turn/interrupt" for m, _ in server.calls)


@pytest.mark.asyncio
async def test_default_native_mode_does_not_construct_gui_backend(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CONTROL_BACKEND", "app-server")
    monkeypatch.setattr(config, "CODEX_APP_SERVER_SOCKET", str(tmp_path / "missing"))
    monkeypatch.setattr("bridge.daemon.create_input_backend", lambda: pytest.fail("GUI backend constructed"))
    daemon = Daemon(Mock(), dictation=Mock())
    send = AsyncMock()
    daemon.agent_control.send = send
    response = await daemon._handle_ipc_action({"action": "agent_sessions"})
    assert response["status"] == "error"
    assert daemon.agent_control.backend.selected_id is None
    await daemon.agent_control.close()


@pytest.mark.asyncio
async def test_overview_counts_sessions_without_requiring_navigation(app_server):
    server, client = app_server
    for i in range(90):
        server.threads[str(i)] = {"id": str(i), "name": "Тест | session", "cwd": "/p", "status": {"type": "idle"}}
    send = AsyncMock()
    control = AgentControl(client, send)
    await control.refresh()
    assert control.menu == ["Attention queue", "/compact", "/interrupt"]
    assert client.selected_id is None
    assert len(control.sessions) == 92
    assert len(send.call_args_list[0].args[0]) < 2048
