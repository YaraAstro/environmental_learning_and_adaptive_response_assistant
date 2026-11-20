import json

import pytest

from elara.cli import main


def test_chat_is_explicitly_a_simulation(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["chat", "Hello"]) == 0
    assert "ELARA [simulation]" in capsys.readouterr().out


def test_settings_are_safe(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["settings", "show"]) == 0
    settings = json.loads(capsys.readouterr().out)
    assert settings["inference"]["provider"] == "mock"


def test_doctor_checks_installed_stack(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["doctor"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["sqlite_fts5"] == "ok"
    assert report["network_requested"] is False
