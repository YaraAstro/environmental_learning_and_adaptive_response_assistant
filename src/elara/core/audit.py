"""Structured action audit contracts with no prompt or raw resource fields."""

from datetime import UTC, datetime
from typing import Literal, Protocol
from uuid import UUID, uuid4

from pydantic import Field

from elara.core.contracts import Contract


class AuditEvent(Contract):
    id: UUID = Field(default_factory=uuid4)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    action_id: UUID
    actor_id: UUID
    session_id: UUID
    kind: Literal["action.decision", "action.started", "action.succeeded", "action.failed"]
    capability: Literal["demo.echo", "unsupported"]
    resource_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    outcome: Literal["allow", "deny"]
    reason: Literal[
        "explicit_scoped_grant", "no_matching_grant", "unsupported_capability_or_resource"
    ]


class AuditSink(Protocol):
    def record(self, event: AuditEvent) -> None: ...
