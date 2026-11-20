from pathlib import Path

import pytest
from pydantic import ValidationError

from elara.core.identity import load_identity
from elara.core.settings import Settings, load_settings


def test_example_config_is_valid_and_creates_no_directories(tmp_path: Path) -> None:
    source = Path(__file__).parents[2] / "config" / "elara.example.toml"
    config = tmp_path / "elara.toml"
    config.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    settings = load_settings(config)
    assert settings.inference.provider == "mock"
    assert settings.inference.cloud_data_policy == "never"
    assert not settings.actions.shell_execution_enabled
    assert settings.data_dir == (tmp_path / "../.data").resolve()
    assert list(tmp_path.iterdir()) == [config]


@pytest.mark.parametrize(
    "values",
    [
        {"actions": {"filesystem_write_enabled": True}},
        {"actions": {"filesystem_read_enabled": True}},
        {"inference": {"provider": "openai"}},
        {"inference": {"allow_silent_cloud_fallback": True}},
        {"inference": {"max_steps_per_request": 0}},
        {"privacy": {"environment_collection_enabled": True}},
        {"learning": {"enabled": True}},
        {"typo_setting": True},
    ],
)
def test_unsupported_or_unsafe_settings_fail(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate(values)


def test_explicit_config_overrides_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    explicit = tmp_path / "explicit.toml"
    explicit.write_text("[inference]\nmax_steps_per_request = 3\n", encoding="utf-8")
    monkeypatch.setenv("ELARA_CONFIG_PATH", str(tmp_path / "missing.toml"))
    assert load_settings(explicit).inference.max_steps_per_request == 3
    with pytest.raises(FileNotFoundError):
        load_settings()


def test_identity_is_frozen_and_blocks_security_edits() -> None:
    identity = load_identity()
    assert identity.principles
    with pytest.raises(ValidationError):
        identity.name = "changed"  # type: ignore[misc, assignment]
    with pytest.raises(ValidationError):
        type(identity).model_validate(
            {**identity.model_dump(), "agent_may_change_constitution": True}
        )
