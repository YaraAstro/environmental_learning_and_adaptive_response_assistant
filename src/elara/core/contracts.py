"""Domain contracts never import agent frameworks or platform adapters."""

from typing import Literal, Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ConversationTurn(Contract):
    role: Literal["user", "assistant"]
    content: str


class AttachedDocument(Contract):
    path: str
    content: str


class MemoryFact(Contract):
    key: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,47}$")
    value: str = Field(min_length=1, max_length=500)


class AgentRequest(Contract):
    message: str = Field(min_length=1, max_length=32_000)
    session_id: UUID = Field(default_factory=uuid4)
    history: tuple[ConversationTurn, ...] = ()
    attachments: tuple[AttachedDocument, ...] = ()
    memories: tuple[MemoryFact, ...] = ()


class AgentResponse(Contract):
    message: str
    session_id: UUID
    simulated: bool


class AgentRuntime(Protocol):
    async def respond(self, request: AgentRequest) -> AgentResponse: ...
