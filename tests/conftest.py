import pytest
from pydantic_ai import models


@pytest.fixture(autouse=True)
def disable_live_models(monkeypatch: pytest.MonkeyPatch) -> None:
    """An accidental switch to a live provider must fail the test suite."""
    monkeypatch.setattr(models, "ALLOW_MODEL_REQUESTS", False)
