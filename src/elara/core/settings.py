"""Validated configuration with explicit mock or local-only Ollama inference."""

import os
import re
import tomllib
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from platformdirs import user_data_path
from pydantic import Field, field_validator, model_validator

from elara.core.contracts import Contract


class InferenceSettings(Contract):
    provider: Literal["mock", "ollama"] = "mock"
    model: str | None = None
    base_url: str = "http://127.0.0.1:11434/v1"
    cloud_data_policy: Literal["never"] = "never"
    allow_silent_cloud_fallback: Literal[False] = False
    max_steps_per_request: int = Field(default=8, ge=1, le=32)
    max_output_tokens: int = Field(default=1024, ge=1, le=8192)
    max_context_characters: int = Field(default=24000, ge=1000, le=128000)
    request_timeout_seconds: float = Field(default=120, ge=1, le=600, allow_inf_nan=False)

    @field_validator("base_url")
    @classmethod
    def local_endpoint_only(cls, value: str) -> str:
        parts = urlsplit(value)
        if (
            parts.scheme != "http"
            or parts.hostname not in {"127.0.0.1", "::1"}
            or parts.username is not None
            or parts.password is not None
            or parts.path not in {"/v1", "/v1/"}
            or parts.query
            or parts.fragment
            or parts.port is None
            or not 1 <= parts.port <= 65535
            or any(character.isspace() for character in value)
        ):
            raise ValueError("Ollama must use a literal loopback HTTP address and /v1 path")
        return value.rstrip("/")

    @field_validator("model")
    @classmethod
    def local_model_only(cls, value: str | None) -> str | None:
        if value is not None and (
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}", value)
            or "cloud" in value.lower()
            or "://" in value
        ):
            raise ValueError("Select a local Ollama model tag; cloud models are not supported")
        return value

    @model_validator(mode="after")
    def model_required(self) -> "InferenceSettings":
        if self.provider == "ollama" and not self.model:
            raise ValueError("Ollama requires an explicit model tag")
        if self.provider == "mock" and self.model is not None:
            raise ValueError("A model tag requires provider = 'ollama'")
        return self


class ActionSettings(Contract):
    default: Literal["deny"] = "deny"
    filesystem_read_enabled: Literal[False] = False
    filesystem_write_enabled: Literal[False] = False
    shell_execution_enabled: Literal[False] = False
    network_actions_enabled: Literal[False] = False


class PrivacySettings(Contract):
    environment_collection_enabled: Literal[False] = False
    telemetry_opt_in: Literal[False] = False


class LearningSettings(Contract):
    enabled: Literal[False] = False
    allow_self_edit_security_controls: Literal[False] = False


class Settings(Contract):
    data_dir: Path = Field(default_factory=lambda: user_data_path("ELARA", appauthor=False))
    sandbox_dir: Path | None = None
    inference: InferenceSettings = Field(default_factory=InferenceSettings)
    actions: ActionSettings = Field(default_factory=ActionSettings)
    privacy: PrivacySettings = Field(default_factory=PrivacySettings)
    learning: LearningSettings = Field(default_factory=LearningSettings)


def load_settings(path: Path | None = None) -> Settings:
    """Explicit path > ELARA_CONFIG_PATH > built-in safe defaults; never reads .env."""
    env_path = os.environ.get("ELARA_CONFIG_PATH")
    selected = path if path is not None else Path(env_path) if env_path else None
    if selected is None:
        return Settings()
    selected = selected.expanduser().resolve(strict=True)
    with selected.open("rb") as handle:
        settings = Settings.model_validate(tomllib.load(handle))
    updates: dict[str, Path] = {}
    for name in ("data_dir", "sandbox_dir"):
        value = getattr(settings, name)
        if isinstance(value, Path):
            value = value.expanduser()
            updates[name] = (selected.parent / value).resolve()
    return settings.model_copy(update=updates)
