import json
from typing import Any

import httpx2 as httpx
import pytest
from pydantic_ai import models

from elara.core.contracts import AgentRequest, ConversationTurn
from elara.core.identity import load_identity
from elara.core.inference import InferenceError
from elara.core.settings import InferenceSettings
from elara.inference import ollama
from elara.inference.ollama import OllamaAgentRuntime


@pytest.fixture
def transport(monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    # Real SDK requests are permitted only after replacing HTTP transport in this fixture.
    calls: list[httpx.Request] = []
    original = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"details": {"format": "gguf"}})
        return httpx.Response(
            200,
            json={
                "id": "synthetic-completion",
                "object": "chat.completion",
                "created": 1,
                "model": "qwen3:4b",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "Hello Alex"},
                    }
                ],
                "usage": {"prompt_tokens": 20, "completion_tokens": 2, "total_tokens": 22},
            },
        )

    monkeypatch.setattr(
        ollama.httpx,
        "AsyncClient",
        lambda **kw: original(transport=httpx.MockTransport(handler), **kw),
    )
    monkeypatch.setattr(models, "ALLOW_MODEL_REQUESTS", True)
    return calls


async def test_real_adapter_replays_history_and_labels_response(
    transport: list[httpx.Request],
) -> None:
    settings = InferenceSettings(provider="ollama", model="qwen3:4b")
    runtime = OllamaAgentRuntime(load_identity(), settings)
    request = AgentRequest(
        message="What is my name?",
        history=(
            ConversationTurn(role="user", content="My name is Alex"),
            ConversationTurn(role="assistant", content="Hello Alex"),
        ),
    )
    result = await runtime.respond(request)
    assert not result.simulated
    assert result.session_id == request.session_id
    assert result.message == "Hello Alex"
    assert [r.url.path for r in transport] == ["/api/show", "/v1/chat/completions"]
    payload = json.loads(transport[-1].content)
    assert [m["content"] for m in payload["messages"] if m["role"] == "user"] == [
        "My name is Alex",
        "What is my name?",
    ]
    assert not payload.get("tools")
    assert payload.get("max_tokens", payload.get("max_completion_tokens")) == 1024
    assert transport[-1].headers["authorization"] == "Bearer ollama-local"


@pytest.mark.parametrize("failure", ["cloud", "connect", "server", "timeout"])
async def test_provider_failures_do_not_fallback_or_leak_details(
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    calls: list[httpx.Request] = []
    original = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if failure == "connect":
            raise httpx.ConnectError("private error text", request=request)
        if failure == "timeout":
            raise httpx.ReadTimeout("private error text", request=request)
        if failure == "cloud":
            return httpx.Response(200, json={"remote_host": "https://ollama.com"})
        return httpx.Response(500, text="private error text")

    def client(**kwargs: Any) -> httpx.AsyncClient:
        return original(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(ollama.httpx, "AsyncClient", client)
    runtime = OllamaAgentRuntime(
        load_identity(), InferenceSettings(provider="ollama", model="qwen3:4b")
    )
    with pytest.raises(InferenceError) as caught:
        await runtime.respond(AgentRequest(message="Private prompt"))
    assert "private" not in str(caught.value).lower()
    assert len(calls) == 1
    assert calls[0].url.path == "/api/show"
