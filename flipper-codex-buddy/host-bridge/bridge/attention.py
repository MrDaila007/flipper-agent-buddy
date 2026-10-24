"""Correlated requests for user attention, shared by every loaded session."""

import re
import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class ChoiceQuestion:
    id: str
    prompt: str
    options: tuple[str, ...]


@dataclass(frozen=True)
class AttentionRequest:
    token: str
    session_id: str
    turn_id: str
    wire_id: str | int
    method: str
    title: str
    detail: str
    params: dict
    yes: dict | None
    no: dict | None
    questions: tuple[ChoiceQuestion, ...] = ()

    @property
    def actionable(self):
        return self.yes is not None and self.no is not None


ATTENTION_METHODS = {
    "item/commandExecution/requestApproval", "item/fileChange/requestApproval",
    "item/permissions/requestApproval", "item/tool/requestUserInput",
    "mcpServer/elicitation/request",
}


def make_attention(message: dict) -> AttentionRequest:
    method, params = message["method"], message["params"]
    title, detail = "Input on PC", params.get("reason") or params.get("message") or "Open Codex"
    yes = no = None
    choice_questions = ()
    if method in {"item/commandExecution/requestApproval", "item/fileChange/requestApproval"}:
        title = "Run" if "commandExecution" in method else "Edit files"
        network = params.get("networkApprovalContext")
        detail = (f"Network: {network.get('host', '')}" if network else
                  params.get("command") or params.get("reason") or params.get("grantRoot") or title)
        decisions = params.get("availableDecisions")
        # Some server policies expose Cancel instead of Decline. Both are
        # explicit negative choices; never invent an unavailable decision.
        negative = "decline" if decisions is None or "decline" in decisions else "cancel" if "cancel" in decisions else None
        if (decisions is None or "accept" in decisions) and negative:
            yes, no = {"decision": "accept"}, {"decision": negative}
    elif method == "item/permissions/requestApproval":
        title = "Permissions"
        permissions = params.get("permissions")
        if isinstance(permissions, dict):
            import json
            detail = params.get("reason") or json.dumps(permissions, ensure_ascii=False)
            yes, no = {"permissions": permissions, "scope": "turn"}, {"permissions": {}, "scope": "turn"}
    elif method == "item/tool/requestUserInput":
        questions = params.get("questions") or []
        detail = " / ".join(q.get("question", "") for q in questions) or "Open Codex"
        if questions and all(
            isinstance(q.get("id"), str) and q["id"] and not q.get("isSecret")
            and q.get("options") and all(isinstance(o.get("label"), str) and o["label"] for o in q["options"])
            for q in questions
        ) and len({q["id"] for q in questions}) == len(questions):
            choice_questions = tuple(ChoiceQuestion(
                q["id"], q.get("question") or q.get("header") or "Choose answer",
                tuple(o["label"] for o in q["options"]),
            ) for q in questions)
            title = "Question"
        if len(questions) == 1 and not questions[0].get("isSecret"):
            q = questions[0]
            options = q.get("options") or []
            positive, negative = [], []
            for option in options:
                label = option["label"]
                normalized = re.sub(r"\s*\([^)]*\)\s*$", "", label).strip().casefold()
                if normalized in {"yes", "allow", "accept", "approve", "да", "разрешить"}:
                    positive.append(label)
                if normalized in {"no", "deny", "decline", "reject", "нет", "отклонить"}:
                    negative.append(label)
            if len(options) == 2 and len(positive) == len(negative) == 1:
                title = "Question"
                yes = {"answers": {q["id"]: {"answers": positive}}}
                no = {"answers": {q["id"]: {"answers": negative}}}
    return AttentionRequest(
        uuid.uuid4().hex, params.get("threadId", ""), params.get("turnId", ""),
        message["id"], method, title, str(detail), params, yes, no, choice_questions,
    )
