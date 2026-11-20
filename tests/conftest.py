from pathlib import Path

import pytest
from pydantic_ai import models

from elara.core.audit import AuditEvent


class MemoryAudit:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def record(self, event: AuditEvent) -> None:
        self.events.append(event)


@pytest.fixture
def audit() -> MemoryAudit:
    return MemoryAudit()


@pytest.fixture(autouse=True)
def isolated_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    directory: Path = tmp_path_factory.mktemp("configuration")
    config = directory / "elara.toml"
    config.write_text('data_dir = "data"\n', encoding="utf-8")
    monkeypatch.setenv("ELARA_CONFIG_PATH", str(config))


@pytest.fixture(autouse=True)
def disable_live_models(monkeypatch: pytest.MonkeyPatch) -> None:
    """An accidental switch to a live provider must fail the test suite."""
    monkeypatch.setattr(models, "ALLOW_MODEL_REQUESTS", False)
