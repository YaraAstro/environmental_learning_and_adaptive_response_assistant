"""Composition root: the sole place that selects the current runtime adapter."""

from elara.core.contracts import AgentRuntime
from elara.core.identity import load_identity
from elara.core.settings import Settings
from elara.inference.mock import MockAgentRuntime
from elara.inference.ollama import OllamaAgentRuntime


def build_runtime(settings: Settings) -> AgentRuntime:
    if settings.inference.provider == "ollama":
        return OllamaAgentRuntime(load_identity(), settings.inference)
    return MockAgentRuntime(load_identity(), settings.inference.max_steps_per_request)
