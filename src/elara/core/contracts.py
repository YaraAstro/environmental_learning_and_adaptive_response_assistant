"""Domain contracts never import agent frameworks or platform adapters."""

from typing import Literal, Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from elara.core.media import AttachedMedia, validate_media_batch


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
    media: tuple[AttachedMedia, ...] = Field(default=(), max_length=10, repr=False)

    @model_validator(mode="after")
    def bounded_media(self) -> "AgentRequest":
        validate_media_batch(self.media)
        return self


class AgentResponse(Contract):
    message: str
    session_id: UUID
    simulated: bool


class AgentRuntime(Protocol):
    async def respond(self, request: AgentRequest) -> AgentResponse: ...
