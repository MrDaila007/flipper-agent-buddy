"""Codex App Server adapter over a local Unix WebSocket.

Observes loaded threads and subscribes to their attention requests. No new
threads/turns, keyboard fallback, or replay of decisions with unknown outcomes.
"""

import asyncio
import json
import logging
from collections import deque
from pathlib import Path

from websockets.asyncio.client import unix_connect

from .agent import AgentBackend, AgentError, AgentRpcError, AgentSession, AgentState
from .attention import ATTENTION_METHODS, make_attention

log = logging.getLogger(__name__)


class CodexAppServer(AgentBackend):
    def __init__(self, socket_path: str, *, timeout: float = 4, confirm_timeout: float = 8):
        self.socket_path = socket_path
        self.timeout = timeout
        self.confirm_timeout = confirm_timeout
        self.selected_id = None
        self._ws = None
        self._request_id = 0
        self._rpc_lock = asyncio.Lock()
        self._interrupt_lock = asyncio.Lock()
        self._send_lock = asyncio.Lock()
        self._reader_task = None
        self._pending = {}
        self.requests = {}
        self._wire_requests = {}
        self._reply_confirm = {}
        self._subscriptions = set()
        self._materialized = set()
        self._unavailable_threads = set()
        self.rate_limits_loaded = False
        self.rate_limits_attempted = False
        self.attention_events = asyncio.Queue()
        self.usage_events = asyncio.Queue()
        self.attention_history = deque(maxlen=20)

    async def _send(self, message):
        async with self._send_lock:
            if self._ws is None:
                raise AgentError("App Server disconnected")
            await self._ws.send(json.dumps(message))

    async def _exchange(self, method: str, params: dict) -> dict:
        self._request_id += 1
        request_id = self._request_id
        future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        try:
            await self._send({"id": request_id, "method": method, "params": params})
            return await future
        finally:
            self._pending.pop(request_id, None)

    @staticmethod
    def _wire_key(value):
        # JSON-RPC string and integer IDs are distinct.
        return (type(value).__name__, value)

    async def _read_loop(self, ws):
        try:
            async for raw in ws:
                message = json.loads(raw)
                if not isinstance(message, dict):
                    raise AgentError("Invalid App Server response")
                method = message.get("method")
                if method:
                    params = message.get("params", {})
                    if method == "thread/tokenUsage/updated":
                        self.usage_events.put_nowait(("context", params))
                    elif method == "account/rateLimits/updated":
                        self.usage_events.put_nowait(("limits", params.get("rateLimits", {})))
                    elif "id" in message and method in ATTENTION_METHODS:
                        key = self._wire_key(message["id"])
                        if key not in self._wire_requests:
                            request = make_attention(message)
                            self.requests[request.token] = request
                            self._wire_requests[key] = request.token
                            log.info("Attention queued: id=%s session=%s kind=%s",
                                     request.token, request.session_id, request.method)
                            self.attention_history.append({
                                "id": request.token, "session_id": request.session_id,
                                "kind": request.method, "actionable": request.actionable or bool(request.questions),
                                "question_count": len(request.questions),
                                "decisions": request.params.get("availableDecisions"), "state": "pending",
                            })
                            log.info("Attention choices: id=%s actionable=%s decisions=%s",
                                     request.token, request.actionable, request.params.get("availableDecisions"))
                            self.attention_events.put_nowait(("request", request))
                    elif method == "serverRequest/resolved":
                        params = message.get("params", {})
                        token = self._wire_requests.get(self._wire_key(params.get("requestId")))
                        request = self.requests.get(token)
                        if request and params.get("threadId") == request.session_id:
                            self._forget_request(request)
                    elif method in {"turn/completed", "thread/closed"}:
                        params = message.get("params", {})
                        turn_id = (params.get("turn") or {}).get("id")
                        for request in list(self.requests.values()):
                            if request.session_id == params.get("threadId") and (
                                method == "thread/closed" or request.turn_id == turn_id
                            ):
                                self._forget_request(request)
                    # Unsupported server requests belong to the normal Codex UI.
                    # Never send an error/decision on another client's behalf.
                    continue
                future = self._pending.get(message.get("id"))
                if future and not future.done():
                    if "error" in message:
                        future.set_exception(AgentRpcError(str(message["error"].get("message", "RPC error"))))
                    elif isinstance(message.get("result"), dict):
                        future.set_result(message["result"])
                    else:
                        future.set_exception(AgentError("Invalid App Server result"))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.info("App Server reader disconnected: %s", exc)
        finally:
            if self._ws is ws:
                self._ws = None
                self._invalidate_requests()
                for future in list(self._pending.values()):
                    if not future.done():
                        future.set_exception(AgentError("App Server disconnected; outcome unknown"))
                await ws.close()

    def _forget_request(self, request):
        log.info("Attention resolved: id=%s session=%s", request.token, request.session_id)
        for record in self.attention_history:
            if record["id"] == request.token:
                record["state"] = "resolved"
        self.requests.pop(request.token, None)
        self._wire_requests.pop(self._wire_key(request.wire_id), None)
        waiter = self._reply_confirm.pop(request.token, None)
        if waiter and not waiter.done():
            waiter.set_result(None)
        self.attention_events.put_nowait(("resolved", request.token))

    def _invalidate_requests(self):
        self.requests.clear()
        self._wire_requests.clear()
        self._subscriptions.clear()
        self._unavailable_threads.clear()
        self.rate_limits_attempted = False
        for future in self._reply_confirm.values():
            if not future.done():
                future.set_exception(AgentError("Connection lost; decision outcome unknown"))
        self._reply_confirm.clear()
        self.attention_events.put_nowait(("disconnected", None))

    async def _drop_connection(self):
        ws, self._ws = self._ws, None
        self._invalidate_requests()
        reader, self._reader_task = self._reader_task, None
        if reader:
            reader.cancel()
            await asyncio.gather(reader, return_exceptions=True)
        if ws:
            await ws.close()

    async def _rpc(self, method: str, params: dict | None = None) -> dict:
        async with self._rpc_lock:
            try:
                return await asyncio.wait_for(self._connected_exchange(method, params or {}), self.timeout)
            except AgentRpcError as exc:
                log.info("App Server RPC %s rejected: %s", method, exc)
                raise
            except asyncio.CancelledError:
                await self._drop_connection()
                raise
            except Exception as exc:
                await self._drop_connection()
                if isinstance(exc, AgentError):
                    raise
                raise AgentError(f"App Server unavailable: {type(exc).__name__}: {exc}") from exc

    async def _connected_exchange(self, method: str, params: dict) -> dict:
        if self._ws is None:
            if self._reader_task:
                await asyncio.gather(self._reader_task, return_exceptions=True)
            self._ws = await unix_connect(
                self.socket_path, open_timeout=self.timeout,
                close_timeout=1, max_size=8 * 1024 * 1024,
            )
            self._reader_task = asyncio.create_task(self._read_loop(self._ws))
            await self._exchange("initialize", {
                "clientInfo": {"name": "flipper_buddy", "version": "0.2.0"},
            })
            await self._send({"method": "initialized", "params": {}})
        return await self._exchange(method, params)

    async def observe_sessions(self):
        sessions = await self.list_sessions()
        live_ids = {s.id for s in sessions}
        self._unavailable_threads.intersection_update(live_ids)
        # Attach only to threads already loaded by the desktop. No overrides or
        # turn/start: subscribing must not start work or change approval policy.
        for session in sessions:
            if session.status == "active":
                self._unavailable_threads.discard(session.id)
            if (session.id in self._materialized and session.id not in self._subscriptions
                    and session.id not in self._unavailable_threads):
                try:
                    await self._rpc("thread/resume", {"threadId": session.id, "excludeTurns": True})
                    self._subscriptions.add(session.id)
                except AgentRpcError as exc:
                    # A stale loaded tab may no longer have a rollout on disk.
                    # Keep all other sessions observable and actionable.
                    self._unavailable_threads.add(session.id)
                    log.info("Skipping unavailable loaded thread %s: %s", session.id, exc)
        return sessions

    async def read_rate_limits(self):
        """Read the initial account usage snapshot; later updates are streamed."""
        self.rate_limits_attempted = True
        try:
            result = await self._rpc("account/rateLimits/read", {})
        except AgentRpcError:
            # This account-level snapshot is optional; a rejection must not
            # disrupt active session observation or approval routing.
            self.rate_limits_loaded = True
            return None
        limits = result.get("rateLimits")
        if isinstance(limits, dict):
            self.rate_limits_loaded = True
            self.usage_events.put_nowait(("limits", limits))
        return limits

    async def list_skills(self, cwds: list[str]):
        result = await self._rpc("skills/list", {"cwds": list(dict.fromkeys(cwds)), "forceReload": True})
        return [skill for entry in result.get("data", []) for skill in entry.get("skills", [])
                if skill.get("enabled") and skill.get("name") and skill.get("path")]

    async def run_skill(self, session_id: str, skill: dict):
        state = await self._state(session_id)
        if state.session.status == "active":
            if not state.turn_id or state.turn_status != "inProgress":
                raise AgentError("Session is busy; wait for its current turn")
            await self._rpc("turn/steer", {
                "threadId": session_id, "expectedTurnId": state.turn_id,
                "input": [{"type": "skill", "name": skill["name"], "path": skill["path"]}],
            })
        else:
            await self._rpc("turn/start", {
                "threadId": session_id,
                "input": [{"type": "skill", "name": skill["name"], "path": skill["path"]}],
            })

    async def compact(self, session_id: str):
        state = await self._state(session_id)
        if state.session.status == "active":
            raise AgentError("Wait for the current turn before compacting")
        await self._rpc("thread/compact/start", {"threadId": session_id})

    async def answer_attention(self, token: str, allow: bool):
        request = self.requests.get(token)
        if not request or not request.actionable:
            raise AgentError("Request expired or needs input in Codex")
        log.info("Attention decision: id=%s session=%s allow=%s", token, request.session_id, allow)
        for record in self.attention_history:
            if record["id"] == token:
                record["reply"] = allow
        await self._answer_request(request, request.yes if allow else request.no)

    async def answer_choices(self, token: str, answers: dict[str, str]):
        request = self.requests.get(token)
        if not request or not request.questions:
            raise AgentError("Question expired or has no selectable options")
        if set(answers) != {q.id for q in request.questions} or any(
            answers[q.id] not in q.options for q in request.questions
        ):
            raise AgentError("Answer must match the original question and options")
        log.info("Attention choices answered: id=%s session=%s questions=%d",
                 token, request.session_id, len(answers))
        await self._answer_request(request, {
            "answers": {question_id: {"answers": [label]} for question_id, label in answers.items()},
        })

    async def _answer_request(self, request, result):
        token = request.token
        if token in self._reply_confirm:
            raise AgentError("Decision already sent; waiting for Codex")
        future = asyncio.get_running_loop().create_future()
        self._reply_confirm[token] = future
        try:
            # Raw JSON-RPC response uses the original server request ID, not a
            # new RPC or the currently selected session. Never reconnect/replay.
            await self._send({"id": request.wire_id, "result": result})
            await asyncio.wait_for(future, self.confirm_timeout)
        except asyncio.TimeoutError as exc:
            raise AgentError("Decision sent; resolution not confirmed") from exc
        except Exception as exc:
            if isinstance(exc, AgentError):
                raise
            raise AgentError(f"Decision outcome unknown: {exc}") from exc
        # Keep a tombstone after timeout/failure until resolved or disconnected.

    @staticmethod
    def _session(thread: dict) -> AgentSession:
        cwd = str(thread.get("cwd") or "")
        return AgentSession(
            id=thread["id"], name=thread.get("name") or Path(cwd).name or thread["id"],
            cwd=cwd, status=(thread.get("status") or {}).get("type", "unknown"),
        )

    async def _loaded_ids(self) -> list[str]:
        ids = []
        cursor = None
        while True:
            params = {"cursor": cursor} if cursor else {}
            page = await self._rpc("thread/loaded/list", params)
            ids.extend(page["data"])
            next_cursor = page.get("nextCursor")
            if not next_cursor:
                return ids
            if next_cursor == cursor:
                raise AgentError("Invalid loaded-thread cursor")
            cursor = next_cursor

    async def list_sessions(self) -> list[AgentSession]:
        sessions = []
        self._materialized = set()
        for thread_id in await self._loaded_ids():
            try:
                result = await self._rpc("thread/read", {"threadId": thread_id})
            except AgentRpcError as exc:
                log.info("Skipping unreadable loaded thread %s: %s", thread_id, exc)
                continue
            session = self._session(result["thread"])
            if result["thread"].get("path") or session.status == "active":
                self._materialized.add(session.id)
            if session.status != "notLoaded":
                sessions.append(session)
        return sessions

    async def _state(self, session_id: str) -> AgentState:
        if session_id not in await self._loaded_ids():
            raise AgentError("Selected session is no longer loaded")
        result = await self._rpc("thread/read", {"threadId": session_id})
        session = self._session(result["thread"])
        if session.status == "notLoaded":
            raise AgentError("Selected session is no longer loaded")
        # Newly opened desktop tabs are loaded but have no materialized turn
        # store until their first prompt. Idle sessions don't need turn history.
        if session.status != "active":
            return AgentState(session)
        turns = await self._rpc("thread/turns/list", {
            "threadId": session_id, "limit": 1, "sortDirection": "desc", "itemsView": "notLoaded",
        })
        latest = next(iter(turns["data"]), {})
        return AgentState(session, latest.get("id"), latest.get("status"))

    async def select_session(self, session_id: str) -> AgentState:
        state = await self._state(session_id)
        self.selected_id = session_id
        return state

    async def get_state(self) -> AgentState:
        if not self.selected_id:
            raise AgentError("Select a session first")
        return await self._state(self.selected_id)

    async def interrupt(self) -> AgentState:
        async with self._interrupt_lock:
            state = await self.get_state()
            return await self._interrupt_state(state)

    async def interrupt_session(self, session_id: str) -> AgentState:
        async with self._interrupt_lock:
            state = await self._state(session_id)
            return await self._interrupt_state(state)

    async def _interrupt_state(self, state: AgentState) -> AgentState:
        # Capture both IDs. Never interrupt a replacement turn or session.
        thread_id, turn_id = state.session.id, state.turn_id
        if state.session.status != "active" or not turn_id or state.turn_status != "inProgress":
            raise AgentError("Selected session has no running turn")
        await self._rpc("turn/interrupt", {"threadId": thread_id, "turnId": turn_id})
        deadline = asyncio.get_running_loop().time() + self.confirm_timeout
        while asyncio.get_running_loop().time() < deadline:
            turns = await self._rpc("thread/turns/list", {
                "threadId": thread_id, "limit": 20,
                "sortDirection": "desc", "itemsView": "notLoaded",
            })
            turn = next((t for t in turns["data"] if t["id"] == turn_id), None)
            if turn and turn["status"] == "interrupted":
                return AgentState(state.session, turn_id, "interrupted")
            if turn and turn["status"] != "inProgress":
                raise AgentError(f"Turn ended as {turn['status']}; interrupt not confirmed")
            await asyncio.sleep(.2)
        raise AgentError("Interrupt sent; outcome not confirmed")

    async def close(self) -> None:
        async with self._rpc_lock:
            await self._drop_connection()
