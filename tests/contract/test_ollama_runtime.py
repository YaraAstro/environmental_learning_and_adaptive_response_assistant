import base64
import io
import json
import wave
from typing import Any

import httpx2 as httpx
import pytest
from pydantic_ai import models

from elara.core.contracts import AgentRequest, ConversationTurn
from elara.core.identity import load_identity
from elara.core.inference import InferenceError
from elara.core.media import AttachedMedia
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
            return httpx.Response(
                200,
                json={
                    "details": {"format": "gguf"},
                    "capabilities": ["completion", "vision", "audio"],
                },
            )
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


async def test_adapter_sends_real_image_and_audio_parts(transport):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\0" * 320)
    image_data = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"fixture").decode()
    audio_data = base64.b64encode(buffer.getvalue()).decode()
    runtime = OllamaAgentRuntime(
        load_identity(), InferenceSettings(provider="ollama", model="local:omni")
    )
    await runtime.respond(
        AgentRequest(
            message="Describe this clip",
            media=(
                AttachedMedia(
                    name="frame.png",
                    mime_type="image/png",
                    data=image_data,
                    source="video_frame",
                    timestamp=1.5,
                ),
                AttachedMedia(
                    name="sound.wav", mime_type="audio/wav", data=audio_data, source="video_audio"
                ),
            ),
        )
    )
    payload = json.loads(transport[-1].content)
    parts = payload["messages"][-1]["content"]
    images = [part for part in parts if part["type"] == "image_url"]
    audios = [part for part in parts if part["type"] == "input_audio"]
    assert images[0]["image_url"]["url"] == f"data:image/png;base64,{image_data}"
    assert audios[0]["input_audio"] == {"format": "wav", "data": audio_data}
    assert "1.5" in parts[0]["text"]
    assert image_data not in parts[0]["text"]
    assert not payload.get("tools")


async def test_missing_media_capability_stops_before_generation(monkeypatch):
    original = httpx.AsyncClient
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200, json={"details": {"format": "gguf"}, "capabilities": ["completion"]}
        )

    monkeypatch.setattr(
        ollama.httpx,
        "AsyncClient",
        lambda **kw: original(transport=httpx.MockTransport(handler), **kw),
    )
    runtime = OllamaAgentRuntime(
        load_identity(), InferenceSettings(provider="ollama", model="text:only")
    )
    image_data = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"fixture").decode()
    with pytest.raises(InferenceError, match="vision"):
        await runtime.respond(
            AgentRequest(
                message="Look",
                media=(
                    AttachedMedia(
                        name="image.png", mime_type="image/png", data=image_data, source="image"
                    ),
                ),
            )
        )
    assert [request.url.path for request in calls] == ["/api/show"]


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
