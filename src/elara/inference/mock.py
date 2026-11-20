"""Exercise real Pydantic AI orchestration with its zero-network test model."""

from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import UsageLimits

from elara.core.contracts import AgentRequest, AgentResponse
from elara.core.identity import IdentityPolicy
from elara.inference.history import model_history

MOCK_MESSAGE = (
    "ELARA's offline foundation is ready. This is a simulated response; "
    "live inference, memory, and environment access are not connected yet."
)


class MockAgentRuntime:
    def __init__(self, identity: IdentityPolicy, max_steps: int = 8) -> None:
        self._agent: Agent[None, str] = Agent(
            TestModel(custom_output_text=MOCK_MESSAGE),
            instructions=identity.instructions(),
        )
        self._max_steps = max_steps

    async def respond(self, request: AgentRequest) -> AgentResponse:
        result = await self._agent.run(
            request.message,
            message_history=model_history(request.history),
            usage_limits=UsageLimits(request_limit=self._max_steps),
        )
        return AgentResponse(message=result.output, session_id=request.session_id, simulated=True)
