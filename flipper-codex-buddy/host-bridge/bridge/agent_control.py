"""Shared attention queue; agent/session selection is an optional PC control."""

import asyncio
import logging
import uuid
from collections import OrderedDict
from dataclasses import asdict
from pathlib import Path

from . import protocol
from .agent import AgentBackend, AgentError

log = logging.getLogger(__name__)


def screen_text(text: str, limit: int = 21) -> str:
    # Existing font is ASCII. Transliterate Russian for display only; replies
    # always retain the original option label, including Unicode and punctuation.
    alphabet = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя", (
        "a", "b", "v", "g", "d", "e", "yo", "zh", "z", "i", "y", "k", "l", "m", "n", "o",
        "p", "r", "s", "t", "u", "f", "kh", "ts", "ch", "sh", "sch", "", "y", "", "e", "yu", "ya",
    )))
    output = []
    for char in text:
        if char.lower() in alphabet:
            translated = alphabet[char.lower()]
            output.append(translated.capitalize() if char.isupper() else translated)
        else:
            output.append(char if 32 <= ord(char) < 127 and char != "|" else " ")
    return "".join(output)[:limit].strip()


class AgentControl:
    def __init__(self, backend: AgentBackend, send):
        self.backend = backend
        self.send = send
        self.sessions = []
        self.menu = ["Attention queue", "/compact", "/interrupt"]
        self._skills = {}
        self._last_display = None
        self._action_lock = asyncio.Lock()
        self._tasks = set()
        self.attention = OrderedDict()
        self._deferred = set()
        self._attention_lock = asyncio.Lock()
        self._shown_token = None
        self._shown_request = None
        self._perm_ids = False
        self._choice_ids = False
        self._choices = {}
        self._show_selected = False
        self._deciding = set()
        self._usage_warning_levels = {"context": 0, "limits": 0}

    def set_capabilities(self, data):
        if data.get("perm_ids") is True:
            self._perm_ids = True
        if data.get("choice_ids") is True:
            self._choice_ids = True

    def current_request(self):
        return next((r for t, r in self.attention.items() if t not in self._deferred), None)

    async def overview(self):
        if self.current_request():
            return await self.present_attention()
        active = sum(s.status == "active" for s in self.sessions)
        await self.send(protocol.state_msg(bool(self.sessions)))
        await self._show(f"{len(self.attention)} need attention" if self.attention else "All clear",
                         f"{len(self.sessions)} sessions, {active} busy")

    async def present_attention(self):
        request = self.current_request()
        if not request:
            return await self.overview()
        session = next((s for s in self.sessions if s.id == request.session_id), None)
        name = (screen_text(session.name) or screen_text(Path(session.cwd).name)) if session else ""
        title = f"1/{len(self.attention)} {request.session_id[-4:]} {name}"
        if request.token in self._deciding:
            await self._show("Waiting for Codex", title)
        elif request.actionable and self._perm_ids:
            display = (request.token, len(self.attention))
            if self._last_display != display:
                detail = screen_text(f"{request.title}: {request.detail}", 63)
                await self.send(protocol.perm_msg(screen_text(title), detail, request.token))
                self._shown_token = request.token
                self._shown_request = request.token
                self._last_display = display
        elif request.questions and self._choice_ids:
            progress = self._choices.setdefault(request.token, {
                "question": 0, "answers": {}, "page": 0, "view_id": uuid.uuid4().hex,
            })
            question = request.questions[progress["question"]]
            start = progress["page"] * 40
            indices = list(range(start, min(start + 40, len(question.options))))
            labels = [screen_text(f"{i + 1}. {question.options[i]}", 26) for i in indices]
            targets = list(indices)
            if start:
                labels.append("Previous options")
                targets.append("previous")
            if start + 40 < len(question.options):
                labels.append("Next options")
                targets.append("next")
            progress["targets"] = targets
            display = (progress["view_id"],)
            if self._last_display != display:
                prompt = screen_text(f"{progress['question'] + 1}/{len(request.questions)} {question.prompt}", 63)
                await self.send(protocol.choice_msg(progress["view_id"], screen_text(title), prompt, labels))
                self._shown_token = progress["view_id"]
                self._shown_request = request.token
                self._last_display = display
        else:
            await self._show("Update Flipper app" if request.actionable or request.questions else "Needs input on PC", title)

    async def attention_events(self):
        while True:
            kind, value = await self.backend.attention_events.get()
            async with self._attention_lock:
                if kind == "request":
                    self.attention.setdefault(value.token, value)
                    self._show_selected = False
                elif kind == "resolved":
                    self.attention.pop(value, None)
                    self._deferred.discard(value)
                    self._deciding.discard(value)
                    self._choices.pop(value, None)
                    if self._shown_request == value:
                        await self.send(protocol.encode("perm_clear", {"id": self._shown_token}))
                        self._shown_token = None
                        self._shown_request = None
                        await self._publish_menu()
                elif kind == "disconnected":
                    self.attention.clear()
                    self._deferred.clear()
                    self._deciding.clear()
                    self._choices.clear()
                    if self._shown_token:
                        await self.send(protocol.encode("perm_clear", {"id": self._shown_token}))
                    self._shown_token = None
                    self._shown_request = None
                    await self._show("Agent unavailable", "Reconnecting")
                    continue
                await self.overview()

    async def reply(self, token, allow):
        async with self._attention_lock:
            current = self.current_request()
            if not token or not current or current.token != token or token in self._deciding:
                log.info("Ignored stale/duplicate Flipper reply: id=%s current=%s",
                         token, current.token if current else None)
                return {"status": "stale_request"}
            self._deciding.add(token)
        try:
            await self.backend.answer_attention(token, allow)
            return {"status": "ok", "request_id": token}
        except AgentError as exc:
            log.warning("Attention reply failed: %s", exc)
            async with self._attention_lock:
                await self.overview()
            return {"status": "error", "error": str(exc)}
        # Never replay an uncertain decision. Server resolution/disconnect clears it.

    async def choose(self, view_id, index):
        async with self._attention_lock:
            request = self.current_request()
            progress = self._choices.get(request.token) if request else None
            if (not request or not progress or progress["view_id"] != view_id
                    or request.token in self._deciding or type(index) is not int):
                return {"status": "stale_request"}
            if index == -1:
                self._deferred.add(request.token)
                progress["view_id"] = uuid.uuid4().hex
                await self.send(protocol.encode("perm_clear", {"id": view_id}))
                self._shown_request = self._shown_token = None
                await self._publish_menu()
                await self.overview()
                return {"status": "deferred"}
            if not 0 <= index < len(progress["targets"]):
                return {"status": "invalid_choice"}
            target = progress["targets"][index]
            if target in {"previous", "next"}:
                progress["page"] += 1 if target == "next" else -1
            else:
                question = request.questions[progress["question"]]
                progress["answers"][question.id] = question.options[target]
                progress["question"] += 1
                progress["page"] = 0
            progress["view_id"] = uuid.uuid4().hex
            if progress["question"] < len(request.questions):
                await self.present_attention()
                return {"status": "next_question"}
            self._deciding.add(request.token)
            answers = dict(progress["answers"])
        try:
            await self.backend.answer_choices(request.token, answers)
            return {"status": "ok", "request_id": request.token}
        except AgentError as exc:
            log.warning("Question reply failed: %s", exc)
            async with self._attention_lock:
                await self.overview()
            return {"status": "error", "error": str(exc)}

    async def _show(self, title: str, detail: str = "", *, sound: str = "none"):
        display = (title, detail, sound)
        if display == self._last_display:
            return
        await self.send(protocol.notify_msg(sound, False, screen_text(title), screen_text(detail)))
        self._last_display = display

    async def refresh(self):
        self.sessions = await self.backend.list_sessions()
        self._skills = {}
        list_skills = getattr(self.backend, "list_skills", None)
        if list_skills:
            try:
                for skill in await list_skills([s.cwd for s in self.sessions if s.cwd]):
                    label = screen_text("/" + skill["name"], 26)
                    if label and label not in self._skills and len(self._skills) < 50:
                        self._skills[label] = skill
            except AgentError as exc:
                log.info("Could not load Codex skills: %s", exc)
        self.menu = ["Attention queue", "/compact", "/interrupt", *self._skills]
        await self._publish_menu()
        await self.overview()
        return {"status": "ok", "sessions": [asdict(s) for s in self.sessions]}

    def _command_target(self, *, idle=False):
        candidates = [s for s in self.sessions if s.status == "idle"] if idle else list(self.sessions)
        if not idle:
            active = [s for s in candidates if s.status == "active"]
            if len(active) == 1:
                return active[0]
        return candidates[0] if len(candidates) == 1 else None

    async def run_command(self, label):
        if label == "Refresh sessions":
            return await self.refresh()
        if label == "/compact":
            target = self._command_target(idle=True)
            if not target:
                await self._show("Choose one idle", "session on PC")
                return {"status": "ambiguous_session"}
            try:
                await self.backend.compact(target.id)
                await self._show("Compacting", screen_text(target.name))
                return {"status": "ok", "session_id": target.id}
            except (AgentError, AttributeError) as exc:
                await self._show("Command failed", str(exc))
                return {"status": "error", "error": str(exc)}
        if label == "/interrupt":
            target = self._command_target()
            if not target or target.status != "active":
                await self._show("Choose active", "session on PC")
                return {"status": "ambiguous_session"}
            try:
                await self.backend.interrupt_session(target.id)
                await self._show("Turn interrupted", screen_text(target.name), sound="interrupt")
                return {"status": "ok", "session_id": target.id}
            except (AgentError, AttributeError) as exc:
                await self._show("Command failed", str(exc))
                return {"status": "error", "error": str(exc)}
        skill = self._skills.get(label)
        if skill:
            target = self._command_target()
            if not target:
                await self._show("Choose session", "select on PC")
                return {"status": "ambiguous_session"}
            try:
                await self.backend.run_skill(target.id, skill)
                await self._show("Skill sent", screen_text(skill["name"]))
                return {"status": "ok", "session_id": target.id}
            except (AgentError, AttributeError) as exc:
                await self._show("Command failed", str(exc))
                return {"status": "error", "error": str(exc)}
        await self._show("Unknown menu item", "Refresh sessions")
        return {"status": "unknown_command"}

    async def _publish_menu(self):
        # Reuse the existing menu for the queue and native Codex commands.
        current = self.current_request()
        if not (current and current.questions and self._shown_request == current.token):
            await self.send(protocol.menu_msg(self.menu))

    async def select(self, session_id):
        state = await self.backend.select_session(session_id)
        self._show_selected = True
        self._last_display = None
        await self.show_state(state)
        return {"status": "ok", "state": asdict(state)}

    async def show_state(self, state):
        if self.attention:
            return
        if state.session.id != self.backend.selected_id:
            return
        name = screen_text(state.session.name) or screen_text(Path(state.session.cwd).name)
        title = {"active": "Working", "idle": "Idle", "systemError": "Agent error"}.get(
            state.session.status, state.session.status,
        )
        title = f"{title} {state.session.id[-4:]}"
        display = (title, name, state.turn_id, state.turn_status)
        if display == self._last_display:
            return
        await self.send(protocol.state_msg(True))
        if state.session.status == "active":
            await self.send(protocol.status_msg(title, name))
        else:
            await self.send(protocol.notify_msg("none", False, title, name))
        self._last_display = display

    async def status(self):
        state = await self.backend.get_state()
        await self.show_state(state)
        return {"status": "ok", "state": asdict(state)}

    async def interrupt(self):
        state = await self.backend.interrupt()
        await self._show("Turn interrupted", state.turn_id[-12:], sound="interrupt")
        return {"status": "ok", "state": asdict(state)}

    async def action(self, action: str, session_id: str = ""):
        async with self._action_lock:
            try:
                if action == "agent_sessions":
                    return await self.refresh()
                if action == "agent_select":
                    return await self.select(session_id)
                if action == "agent_status":
                    return await self.status()
                if action == "agent_interrupt":
                    return await self.interrupt()
                raise AgentError("Unsupported agent action")
            except AgentError as exc:
                log.warning("Native agent action failed: %s", exc)
                await self._show("Agent command failed", str(exc))
                return {"status": "error", "error": str(exc)}

    async def handle(self, msg):
        kind, data = msg.get("t"), msg.get("d", {})
        if kind == "perm_resp":
            await self.reply(data.get("id"), data.get("allow") is True and not data.get("esc"))
        elif kind == "choice_resp":
            await self.choose(data.get("id"), data.get("index"))
        elif kind in {"enter", "yes", "esc", "interrupt", "backspace"}:
            async with self._attention_lock:
                current = self.current_request()
                if current and not current.actionable and not current.questions:
                    self._deferred.add(current.token)
                elif not current:
                    self._deferred.clear()
                self._show_selected = False
                await self.overview()
        elif kind == "cmd":
            label = data.get("text", "")
            if label == "Attention queue":
                async with self._attention_lock:
                    self._deferred.clear()
                    self._show_selected = False
                    await self.overview()
            else:
                await self.run_command(label)
        else:
            await self._show("Unavailable", "Native agent mode")

    def dispatch(self, msg):
        # Keep USB read/ping responsive while an RPC waits for confirmation.
        if self._tasks and msg.get("t") not in {"perm_resp", "choice_resp"}:
            log.info("Native action already pending; ignoring repeated button")
            return
        task = asyncio.create_task(self.handle(msg))
        self._tasks.add(task)
        task.add_done_callback(self._finished)

    def _finished(self, task):
        self._tasks.discard(task)
        if not task.cancelled() and task.exception():
            log.error("Native control task failed: %s", task.exception())

    def invalidate_display(self):
        self._last_display = None
        self._perm_ids = False
        self._choice_ids = False
        self._shown_token = None
        self._shown_request = None

    async def monitor(self):
        events = asyncio.create_task(self.attention_events())
        usage_queue = getattr(self.backend, "usage_events", None)
        usage_events = asyncio.create_task(self._usage_events(usage_queue)) if usage_queue else None
        read_limits = getattr(self.backend, "read_rate_limits", None)
        try:
            while True:
                try:
                    if read_limits and not getattr(self.backend, "rate_limits_attempted", False):
                        try:
                            await read_limits()
                        except AgentError as exc:
                            # Quota snapshots are optional; keep session and
                            # approval monitoring available without them.
                            log.info("Initial Codex rate limits unavailable: %s", exc)
                    self.sessions = await self.backend.observe_sessions()
                    if self._show_selected and self.backend.selected_id and not self.attention:
                        await self.status()
                    else:
                        async with self._attention_lock:
                            await self.overview()
                except AgentError as exc:
                    log.debug("Codex monitor read failed: %s", exc)
                    await self.send(protocol.state_msg(False))
                    await self._show("Agent unavailable", str(exc))
                await asyncio.sleep(2)
        finally:
            events.cancel()
            if usage_events:
                usage_events.cancel()
            await asyncio.gather(*(t for t in (events, usage_events) if t), return_exceptions=True)

    @staticmethod
    def _limit_percent(limits):
        values = []
        for window in (limits.get("primary"), limits.get("secondary")):
            if isinstance(window, dict):
                value = window.get("usedPercent", window.get("used_percent"))
                if isinstance(value, (int, float)):
                    values.append(max(0, min(100, int(round(value)))))
        return max(values) if values else None

    async def _usage_events(self, queue):
        while True:
            kind, value = await queue.get()
            if kind == "context":
                usage = value.get("tokenUsage") or {}
                last = usage.get("last") or {}
                window = usage.get("modelContextWindow")
                tokens = last.get("totalTokens")
                try:
                    context_pct = max(0, min(100, round(int(tokens) * 100 / int(window))))
                except (TypeError, ValueError, ZeroDivisionError):
                    context_pct = None
                if context_pct is not None:
                    await self.send(protocol.usage_msg(context_pct=context_pct))
                    await self._warn_usage("context", context_pct)
            elif kind == "limits":
                limits = value.get("rateLimits", value) if isinstance(value, dict) else {}
                session_pct = self._limit_percent(limits)
                if session_pct is not None:
                    await self.send(protocol.usage_msg(session_pct=session_pct))
                    await self._warn_usage("limits", session_pct)

    async def _warn_usage(self, kind, percent):
        level = 2 if percent >= 95 else 1 if percent >= 80 else 0
        previous = self._usage_warning_levels[kind]
        self._usage_warning_levels[kind] = level
        if level <= previous:
            return
        label = "Context" if kind == "context" else "Codex limit"
        sound = "alert" if level == 2 else "ready"
        await self.send(protocol.notify_msg(sound, True, f"{label} {percent}%", "Usage is high"))

    async def close(self):
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        await self.backend.close()
