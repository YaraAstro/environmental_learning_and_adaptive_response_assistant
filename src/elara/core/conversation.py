"""Load history and atomically persist successful conversation exchanges."""

from uuid import UUID

from elara.core.contracts import AgentRequest, AgentResponse, AgentRuntime, AttachedDocument
from elara.core.sessions import SessionRepository


class ConversationService:
    def __init__(self, runtime: AgentRuntime, sessions: SessionRepository) -> None:
        self._runtime = runtime
        self._sessions = sessions

    async def respond(
        self, session_id: UUID, message: str, *, attachments: tuple[AttachedDocument, ...] = ()
    ) -> AgentResponse:
        snapshot = self._sessions.snapshot(session_id)
        request = AgentRequest(
            message=message, session_id=session_id, history=snapshot.turns, attachments=attachments
        )
        response = await self._runtime.respond(request)
        if response.session_id != session_id:
            raise ValueError("Runtime returned a response for a different session")
        self._sessions.append_exchange(
            session_id,
            message,
            response.message,
            simulated=response.simulated,
            expected_revision=snapshot.session.revision,
        )
        return response
