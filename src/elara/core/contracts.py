"""Domain contracts never import agent frameworks or platform adapters."""

from typing import Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AgentRequest(Contract):
    message: str = Field(min_length=1, max_length=32_000)
    session_id: UUID = Field(default_factory=uuid4)


class AgentResponse(Contract):
    message: str
    session_id: UUID
    simulated: bool


class AgentRuntime(Protocol):
    async def respond(self, request: AgentRequest) -> AgentResponse: ...
