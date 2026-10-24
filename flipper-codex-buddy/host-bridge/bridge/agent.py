"""Agent attention is shared across sessions; targeted commands are optional."""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass


class AgentError(Exception):
    """A command failed or its outcome couldn't be confirmed."""


class AgentRpcError(AgentError):
    """The server rejected one RPC while its connection remains usable."""


@dataclass(frozen=True)
class AgentSession:
    id: str
    name: str
    cwd: str
    status: str


@dataclass(frozen=True)
class AgentState:
    session: AgentSession
    turn_id: str | None = None
    turn_status: str | None = None


class AgentBackend(ABC):
    selected_id: str | None = None
    attention_events: asyncio.Queue

    @abstractmethod
    async def observe_sessions(self) -> list[AgentSession]: ...

    @abstractmethod
    async def answer_attention(self, token: str, allow: bool) -> None: ...

    @abstractmethod
    async def answer_choices(self, token: str, answers: dict[str, str]) -> None: ...

    @abstractmethod
    async def list_sessions(self) -> list[AgentSession]: ...

    @abstractmethod
    async def select_session(self, session_id: str) -> AgentState: ...

    @abstractmethod
    async def get_state(self) -> AgentState: ...

    @abstractmethod
    async def interrupt(self) -> AgentState: ...

    @abstractmethod
    async def close(self) -> None: ...
