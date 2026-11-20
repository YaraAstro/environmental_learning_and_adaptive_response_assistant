import json
from pathlib import Path

import pytest

from elara.cli import main
from elara.core.inference import InferenceError
from elara.core.settings import load_settings
from elara.inference import ollama


def test_mock_provider_check_needs_no_network_or_storage(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["provider", "check"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "simulation"
    assert report["generation_tested"] is False
    assert not load_settings().data_dir.exists()


def test_provider_check_reports_safe_failure_and_no_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = tmp_path / "elara.toml"
    config.write_text('data_dir = "data"\n[inference]\nprovider = "ollama"\nmodel = "qwen3:4b"\n')

    def fail(*args: object) -> None:
        raise InferenceError("Cannot reach local Ollama.")

    monkeypatch.setattr(ollama, "check_ollama", fail)
    assert main(["--config", str(config), "provider", "check"]) == 1
    assert "Cannot reach local Ollama" in capsys.readouterr().err
    assert not (tmp_path / "data").exists()


def test_ready_check_does_not_claim_generation_was_tested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = tmp_path / "elara.toml"
    config.write_text('[inference]\nprovider = "ollama"\nmodel = "qwen3:4b"\n')
    monkeypatch.setattr(ollama, "check_ollama", lambda settings: None)
    assert main(["--config", str(config), "provider", "check"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "ready"
    assert report["generation_tested"] is False
