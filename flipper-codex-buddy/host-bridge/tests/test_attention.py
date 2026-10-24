import asyncio
import json
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from bridge.agent_control import AgentControl
from bridge.attention import make_attention
from bridge.agent import AgentError
from .test_agent_codex import app_server  # reuse a real local Unix WebSocket


async def until(predicate):
    async def wait():
        while not predicate():
            await asyncio.sleep(.005)
    await asyncio.wait_for(wait(), 2)


@pytest_asyncio.fixture
async def queue_control(app_server):
    server, client = app_server
    control = AgentControl(client, AsyncMock())
    control.set_capabilities({"perm_ids": True})
    task = asyncio.create_task(control.monitor())
    await server.subscribed.wait()
    try:
        yield server, client, control
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await control.close()


@pytest.mark.asyncio
async def test_fifo_across_sessions_with_exact_yes_no_and_no_selection(queue_control):
    server, client, control = queue_control
    await server.send_request(1001, "a", command="echo first")
    await server.send_request("1002", "b", command="echo second")
    await until(lambda: len(control.attention) == 2)
    first, second = list(control.attention.values())
    assert client.selected_id is None
    assert first.session_id == "a" and second.session_id == "b"
    await control.handle({"t": "perm_resp", "d": {"id": first.token, "allow": True}})
    await until(lambda: list(control.attention) == [second.token])
    assert server.answers[0] == {"id": 1001, "result": {"decision": "accept"}}
    await control.handle({"t": "perm_resp", "d": {"id": second.token, "allow": False}})
    await until(lambda: not control.attention)
    assert server.answers[1] == {"id": "1002", "result": {"decision": "decline"}}
    assert any(json.loads(c.args[0])["d"].get("text") == "All clear" for c in control.send.call_args_list)


@pytest.mark.asyncio
async def test_external_resolution_removes_request_and_stale_button_cannot_answer_next(queue_control):
    server, client, control = queue_control
    await server.send_request(1001)
    await server.send_request(1002, "b")
    await until(lambda: len(control.attention) == 2)
    old, next_request = list(control.attention.values())
    await server.resolve(1001)
    await until(lambda: list(control.attention) == [next_request.token])
    for token in [old.token, None, "wrong"]:
        assert await control.reply(token, True) == {"status": "stale_request"}
    assert server.answers == []


@pytest.mark.asyncio
async def test_duplicate_delivery_and_duplicate_button_only_answer_once(queue_control):
    server, client, control = queue_control
    await server.send_request(1001)
    await server.send_request(1001)
    await until(lambda: len(control.attention) == 1)
    request = control.current_request()
    await asyncio.gather(control.reply(request.token, True), control.reply(request.token, True))
    assert len(server.answers) == 1


@pytest.mark.asyncio
async def test_unconfirmed_answer_never_replays(queue_control):
    server, client, control = queue_control
    server.resolve_answers = False
    await server.send_request(1001)
    await until(lambda: len(control.attention) == 1)
    request = control.current_request()
    response = await control.reply(request.token, True)
    assert response["status"] == "error"
    assert request.token in control.attention
    await control.reply(request.token, True)
    assert len(server.answers) == 1
    await server.resolve(1001)
    await until(lambda: not control.attention)


@pytest.mark.asyncio
async def test_disconnect_invalidates_tokens_and_never_auto_answers(queue_control):
    server, client, control = queue_control
    await server.send_request(1001)
    await until(lambda: len(control.attention) == 1)
    request = control.current_request()
    await client._drop_connection()
    await until(lambda: not control.attention)
    assert await control.reply(request.token, True) == {"status": "stale_request"}
    assert not server.answers


@pytest.mark.asyncio
async def test_old_firmware_gets_update_notice_not_unsafe_idless_approval(queue_control):
    server, client, control = queue_control
    control._perm_ids = False
    control.send.reset_mock()
    await server.send_request(1001)
    await until(lambda: len(control.attention) == 1)
    assert not any(json.loads(c.args[0])["t"] == "perm" for c in control.send.call_args_list)
    await control.handle({"t": "perm_resp", "d": {"allow": True}})
    assert not server.answers


@pytest.mark.asyncio
async def test_freeform_questions_are_shown_and_deferred_without_fabricated_answer(queue_control):
    server, client, control = queue_control
    await server.send_request(1001, method="item/tool/requestUserInput", questions=[{
        "id": "q", "question": "Enter database name", "options": None,
    }])
    await server.send_request(1002, "b")
    await until(lambda: len(control.attention) == 2)
    first, second = list(control.attention.values())
    assert not first.actionable
    await control.handle({"t": "enter"})
    assert control.current_request().token == second.token
    assert not server.answers


def test_binary_question_keeps_original_question_and_option_ids():
    request = make_attention({"id": "server-id", "method": "item/tool/requestUserInput", "params": {
        "threadId": "session", "turnId": "turn", "questions": [{
            "id": "approve-deploy", "question": "Proceed?",
            "options": [{"label": "Yes (Recommended)"}, {"label": "No"}],
        }],
    }})
    assert request.yes == {"answers": {"approve-deploy": {"answers": ["Yes (Recommended)"]}}}
    assert request.no == {"answers": {"approve-deploy": {"answers": ["No"]}}}


def test_policy_with_accept_cancel_still_offers_yes_no():
    request = make_attention({"id": 1, "method": "item/commandExecution/requestApproval", "params": {
        "threadId": "a", "turnId": "t", "command": "echo test",
        "availableDecisions": ["accept", "cancel"],
    }})
    assert request.actionable
    assert request.yes == {"decision": "accept"}
    assert request.no == {"decision": "cancel"}


@pytest.mark.asyncio
async def test_second_button_is_not_dropped_while_first_handler_finishes(queue_control):
    server, client, control = queue_control
    await server.send_request(1001)
    await server.send_request(1002, "b")
    await until(lambda: len(control.attention) == 2)
    first, second = list(control.attention.values())
    release = asyncio.Event()
    original = client.answer_attention

    async def slow_finish(token, allow):
        await original(token, allow)
        if token == first.token:
            await release.wait()

    client.answer_attention = slow_finish
    control.dispatch({"t": "perm_resp", "d": {"id": first.token, "allow": True}})
    await until(lambda: control.current_request().token == second.token)
    control.dispatch({"t": "perm_resp", "d": {"id": second.token, "allow": False}})
    await until(lambda: len(server.answers) == 2)
    release.set()
    await asyncio.gather(*control._tasks)
    assert server.answers[1]["id"] == 1002


async def choice_request(queue_control, questions, request_id=2001):
    server, client, control = queue_control
    control.set_capabilities({"choice_ids": True})
    await server.send_request(request_id, method="item/tool/requestUserInput", questions=questions)
    await until(lambda: control.current_request() is not None)
    await until(lambda: any(json.loads(c.args[0])["t"] == "choice" for c in control.send.call_args_list))
    return control.current_request()


@pytest.mark.asyncio
async def test_multiple_choice_sends_original_unicode_label_not_display_text(queue_control):
    server, client, control = queue_control
    request = await choice_request(queue_control, [{
        "id": "database", "question": 'Какую "базу" выбрать?', "options": [
            {"label": "Postgres"}, {"label": "Локальная SQLite"}, {"label": "Memory"},
        ],
    }])
    view = control._choices[request.token]["view_id"]
    frame = next(json.loads(c.args[0]) for c in control.send.call_args_list if json.loads(c.args[0])["t"] == "choice")
    assert "Lokalnaya SQLite" in frame["d"]["items"]
    assert '"bazu"' in frame["d"]["text"]
    await control.handle({"t": "choice_resp", "d": {"id": view, "index": 1}})
    await until(lambda: not control.attention)
    assert server.answers == [{"id": 2001, "result": {
        "answers": {"database": {"answers": ["Локальная SQLite"]}},
    }}]


@pytest.mark.asyncio
async def test_question_batch_sends_once_after_all_answers_and_rejects_old_screen(queue_control):
    server, client, control = queue_control
    request = await choice_request(queue_control, [
        {"id": "db", "question": "Which DB?", "options": [{"label": "A"}, {"label": "B"}]},
        {"id": "region", "question": "Which region?", "options": [{"label": "EU"}, {"label": "US"}]},
    ])
    first = control._choices[request.token]["view_id"]
    assert (await control.choose(first, 1))["status"] == "next_question"
    assert not server.answers
    second = control._choices[request.token]["view_id"]
    assert second != first
    assert await control.choose(first, 0) == {"status": "stale_request"}
    await control.choose(second, 0)
    assert server.answers[0]["result"] == {"answers": {
        "db": {"answers": ["B"]}, "region": {"answers": ["EU"]},
    }}


@pytest.mark.asyncio
async def test_option_pagination_uses_new_view_ids_and_original_indices(queue_control):
    server, client, control = queue_control
    request = await choice_request(queue_control, [{
        "id": "q", "question": "Choose", "options": [{"label": f"Option {i}"} for i in range(91)],
    }])
    first = control._choices[request.token]["view_id"]
    await control.choose(first, 40)  # Next options
    second = control._choices[request.token]["view_id"]
    assert second != first
    assert not server.answers
    assert await control.choose(first, 2) == {"status": "stale_request"}
    assert await control.choose(second, 999) == {"status": "invalid_choice"}
    assert await control.choose(second, True) == {"status": "stale_request"}
    await control.choose(second, 3)
    assert server.answers[0]["result"]["answers"]["q"]["answers"] == ["Option 43"]
    assert all(len(c.args[0]) < 2048 for c in control.send.call_args_list)


@pytest.mark.asyncio
async def test_choice_back_defers_without_answer_and_expiry_rejects_old_choice(queue_control):
    server, client, control = queue_control
    request = await choice_request(queue_control, [{
        "id": "q", "question": "Choose", "options": [{"label": "A"}, {"label": "B"}],
    }])
    view = control._choices[request.token]["view_id"]
    assert await control.choose(view, -1) == {"status": "deferred"}
    assert not server.answers
    await control.handle({"t": "cmd", "d": {"text": "Attention queue"}})
    assert control._choices[request.token]["view_id"] != view
    await server.resolve(2001)
    await until(lambda: not control.attention)
    assert await control.choose(view, 0) == {"status": "stale_request"}
    assert not server.answers


@pytest.mark.asyncio
async def test_backend_rejects_fabricated_or_incomplete_option_answers(queue_control):
    server, client, control = queue_control
    request = await choice_request(queue_control, [{
        "id": "q", "question": "Choose", "options": [{"label": "A"}, {"label": "B"}],
    }])
    for answers in [{}, {"wrong": "A"}, {"q": "not an option"}]:
        with pytest.raises(AgentError):
            await client.answer_choices(request.token, answers)
    assert not server.answers


@pytest.mark.asyncio
async def test_session_refresh_does_not_replace_active_choice_menu(queue_control):
    server, client, control = queue_control
    request = await choice_request(queue_control, [{
        "id": "q", "question": "Choose", "options": [{"label": "A"}, {"label": "B"}],
    }])
    view = control._choices[request.token]["view_id"]
    control.send.reset_mock()
    await control.refresh()
    assert not any(json.loads(c.args[0])["t"] in {"menu", "choice"} for c in control.send.call_args_list)
    assert control._choices[request.token]["view_id"] == view


@pytest.mark.parametrize("questions", [
    [{"id": "q", "question": "Password", "isSecret": True, "options": [{"label": "A"}]}],
    [{"id": "q", "question": "Free text", "options": None}],
    [{"id": "same", "options": [{"label": "A"}]}, {"id": "same", "options": [{"label": "B"}]}],
])
def test_unsupported_question_shapes_are_not_mapped_to_choices(questions):
    request = make_attention({"id": 1, "method": "item/tool/requestUserInput", "params": {
        "threadId": "a", "turnId": "t", "questions": questions,
    }})
    assert not request.questions
    assert not request.actionable
