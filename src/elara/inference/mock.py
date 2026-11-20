"""Exercise real Pydantic AI orchestration with its zero-network test model."""

from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import UsageLimits

from elara.core.contracts import AgentRequest, AgentResponse
from elara.core.identity import IdentityPolicy

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
        history: list[ModelMessage] = []
        for turn in request.history:
            if turn.role == "user":
                history.append(ModelRequest(parts=[UserPromptPart(content=turn.content)]))
            else:
                history.append(ModelResponse(parts=[TextPart(content=turn.content)]))
        result = await self._agent.run(
            request.message,
            message_history=history,
            usage_limits=UsageLimits(request_limit=self._max_steps),
        )
        return AgentResponse(message=result.output, session_id=request.session_id, simulated=True)
