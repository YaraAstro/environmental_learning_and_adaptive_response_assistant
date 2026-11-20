"""Provider-independent session persistence contracts."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from elara.core.contracts import Contract, ConversationTurn


class Session(Contract):
    id: UUID
    created_at: datetime
    revision: int = 0


class SessionSnapshot(Contract):
    session: Session
    turns: tuple[ConversationTurn, ...]


class SessionNotFound(ValueError):
    """The supplied session does not exist; do not silently create a replacement."""


class SessionConflict(ValueError):
    """The session changed while a response was being generated."""


class SessionRepository(Protocol):
    def snapshot(self, session_id: UUID) -> SessionSnapshot: ...

    def append_exchange(
        self,
        session_id: UUID,
        user_message: str,
        assistant_message: str,
        *,
        simulated: bool,
        expected_revision: int,
    ) -> None: ...
