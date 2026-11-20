"""Validated v0.0 settings; unsupported capabilities cannot be switched on."""

import os
import tomllib
from pathlib import Path
from typing import Literal

from platformdirs import user_data_path
from pydantic import Field

from elara.core.contracts import Contract


class InferenceSettings(Contract):
    provider: Literal["mock"] = "mock"
    cloud_data_policy: Literal["never"] = "never"
    allow_silent_cloud_fallback: Literal[False] = False
    max_steps_per_request: int = Field(default=8, ge=1, le=32)


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
