import json
from pathlib import Path
from typing import Any

import httpx2 as httpx
import pytest
from pydantic import ValidationError

from elara.app import build_runtime
from elara.core.contracts import AgentRequest, ConversationTurn
from elara.core.identity import load_identity
from elara.core.inference import InferenceError
from elara.core.settings import InferenceSettings, Settings, load_settings
from elara.inference import ollama
from elara.inference.history import model_history
from elara.inference.ollama import OllamaAgentRuntime, check_ollama, validate_local_model


def local_settings(**overrides: Any) -> InferenceSettings:
    return InferenceSettings.model_validate(
        {"provider": "ollama", "model": "qwen3:4b", **overrides}
    )


def test_local_profile_selects_real_adapter_without_network() -> None:
    path = Path(__file__).parents[2] / "config/elara.ollama.example.toml"
    settings = load_settings(path)
    assert settings.inference.cloud_data_policy == "never"
    assert isinstance(build_runtime(settings), OllamaAgentRuntime)


@pytest.mark.parametrize(
    "url",
    [
        "https://ollama.com/v1",
        "http://example.com:11434/v1",
        "http://localhost:11434/v1",
        "http://127.0.0.1.example.com:11434/v1",
        "http://127.0.0.1:11434/v1?redirect=cloud",
        "http://user:secret@127.0.0.1:11434/v1",
        "http://127.0.0.1:11434/other",
        "http://127.0.0.1:11434/v1#cloud",
        "http://127.0.0.1:0/v1",
        "http://127.0.0.1/v1",
        " http://127.0.0.1:11434/v1",
        "http://127.0.0.1:11434/v1\n",
    ],
)
def test_remote_or_ambiguous_endpoints_are_rejected(url: str) -> None:
    with pytest.raises(ValidationError):
        local_settings(base_url=url)


@pytest.mark.parametrize("model", [None, "", "qwen3:cloud", "gpt-oss:120b-cloud", "x\ny"])
def test_missing_or_cloud_models_are_rejected(model: str | None) -> None:
    with pytest.raises(ValidationError):
        local_settings(model=model)


def test_ipv6_and_trailing_slash_are_normalized() -> None:
    assert local_settings(base_url="http://[::1]:11434/v1/").base_url == "http://[::1]:11434/v1"


@pytest.mark.parametrize(
    "values",
    [
        {"max_output_tokens": 0},
        {"request_timeout_seconds": float("nan")},
        {"request_timeout_seconds": 0},
        {"cloud_data_policy": "allow"},
        {"allow_silent_cloud_fallback": True},
        {"max_context_characters": 0},
    ],
)
def test_invalid_limits_and_cloud_policy_are_rejected(values: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        local_settings(**values)


@pytest.mark.parametrize(
    "body",
    [
        {},
        [],
        {"details": {}},
        {"details": {"format": "gguf"}, "remote_host": "https://ollama.com"},
        {"details": {"format": "gguf"}, "remote_model": "aliased-cloud-model"},
    ],
)
def test_cloud_aliases_and_unknown_model_metadata_are_rejected(body: Any) -> None:
    with pytest.raises(InferenceError):
        validate_local_model(httpx.Response(200, json=body))


@pytest.mark.parametrize("status", [301, 307, 401, 404, 500])
def test_metadata_errors_do_not_echo_server_body(status: int) -> None:
    with pytest.raises(InferenceError) as caught:
        validate_local_model(httpx.Response(status, text="private server body"))
    assert "private" not in str(caught.value)


def test_valid_local_metadata_is_accepted() -> None:
    validate_local_model(httpx.Response(200, json={"details": {"format": "gguf"}}))


def test_provider_check_sends_only_model_metadata_and_disables_proxies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[httpx.Request] = []
    options: dict[str, Any] = {}
    original = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"details": {"format": "gguf"}})

    def client(**kwargs: Any) -> httpx.Client:
        options.update(kwargs)
        return original(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(ollama.httpx, "Client", client)
    check_ollama(local_settings())
    assert options["trust_env"] is False
    assert options["follow_redirects"] is False
    assert str(calls[0].url) == "http://127.0.0.1:11434/api/show"
    assert json.loads(calls[0].content) == {"model": "qwen3:4b"}


def test_context_limit_rejects_history_before_any_network() -> None:
    runtime = OllamaAgentRuntime(load_identity(), local_settings(max_context_characters=1000))
    request = AgentRequest(
        message="Hello", history=(ConversationTurn(role="user", content="x" * 1001),)
    )
    with pytest.raises(InferenceError, match="input size"):
        runtime.validate_request(request)


def test_history_translation_preserves_role_order() -> None:
    turns = (
        ConversationTurn(role="user", content="My name is Alex"),
        ConversationTurn(role="assistant", content="Hello Alex"),
    )
    history = model_history(turns)
    assert [message.kind for message in history] == ["request", "response"]
    assert [message.parts[0].content for message in history] == ["My name is Alex", "Hello Alex"]


def test_default_provider_remains_mock() -> None:
    assert Settings().inference.provider == "mock"


def test_sdk_construction_ignores_cloud_environment_and_disables_tracing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pydantic_ai.models.ollama import OllamaModel

    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-used")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("OLLAMA_API_KEY", "must-not-be-used")
    monkeypatch.setenv("OLLAMA_BASE_URL", "https://ollama.com/v1")
    # A never-opened in-memory transport needs no network or event loop.
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    agent = OllamaAgentRuntime(load_identity(), local_settings()).build_agent(client)
    assert isinstance(agent.model, OllamaModel)
    assert agent.model.client.api_key == "ollama-local"
    assert str(agent.model.client.base_url) == "http://127.0.0.1:11434/v1/"
    assert agent.model.client.max_retries == 0
    assert agent.instrument is False
