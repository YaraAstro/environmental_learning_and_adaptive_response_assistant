"""Read explicit user facts afresh for each turn; model output cannot write memory."""

from pathlib import Path

from elara.core.contracts import AgentRequest, AgentResponse, AgentRuntime
from elara.memory.store import SQLiteStore


class MemoryRuntime:
    def __init__(self, runtime: AgentRuntime, path: Path) -> None:
        self._runtime = runtime
        self._path = path

    def prepare(self, request: AgentRequest) -> AgentRequest:
        facts = SQLiteStore(self._path).memories() if self._path.is_file() else ()
        return request.model_copy(update={"memories": facts})

    async def respond(self, request: AgentRequest) -> AgentResponse:
        return await self._runtime.respond(self.prepare(request))
