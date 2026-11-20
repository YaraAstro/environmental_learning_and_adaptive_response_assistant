"""Translate domain conversation history at the framework boundary."""

from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, UserPromptPart

from elara.core.contracts import ConversationTurn


def model_history(turns: tuple[ConversationTurn, ...]) -> list[ModelMessage]:
    history: list[ModelMessage] = []
    for turn in turns:
        if turn.role == "user":
            history.append(ModelRequest(parts=[UserPromptPart(content=turn.content)]))
        else:
            history.append(ModelResponse(parts=[TextPart(content=turn.content)]))
    return history
