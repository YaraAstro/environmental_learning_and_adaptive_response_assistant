import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from elara.cli import main
from elara.core.settings import load_settings


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


def test_temporary_chat_and_session_listing_do_not_create_data(
    capsys: pytest.CaptureFixture[str],
) -> None:
    data_dir = load_settings().data_dir
    assert main(["chat", "Keep this temporary"]) == 0
    assert main(["sessions", "list"]) == 0
    assert not data_dir.exists()


def test_saved_session_resumes_in_a_fresh_process(tmp_path: Path) -> None:
    def run(*arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "elara", *arguments],
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            timeout=45,
            check=True,
        )

    run("chat", "First message", "--save")
    sessions = json.loads(run("sessions", "list").stdout)
    session_id = sessions[0]["id"]
    run("chat", "Second message", "--session", session_id)
    snapshot = json.loads(run("sessions", "show", session_id).stdout)
    assert snapshot["session"]["revision"] == 2
    assert [turn["content"] for turn in snapshot["turns"] if turn["role"] == "user"] == [
        "First message",
        "Second message",
    ]
    export_path = tmp_path / "session.json"
    run("sessions", "export", session_id, "--output", str(export_path))
    assert json.loads(export_path.read_text(encoding="utf-8")) == snapshot
    run("sessions", "delete", session_id)
    assert json.loads(run("sessions", "list").stdout) == []


def test_unknown_session_reports_error_without_creating_database(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from uuid import uuid4

    assert main(["chat", "Hello", "--session", str(uuid4())]) == 1
    assert "session not found" in capsys.readouterr().err
    assert not load_settings().data_dir.exists()


def test_export_and_backup_refuse_existing_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["chat", "Hello", "--save"]) == 0
    capsys.readouterr()
    assert main(["sessions", "list"]) == 0
    session_id = json.loads(capsys.readouterr().out)[0]["id"]
    target = tmp_path / "protected.txt"
    target.write_text("keep this", encoding="utf-8")
    assert main(["sessions", "export", session_id, "--output", str(target)]) == 1
    assert main(["database", "backup", str(target)]) == 1
    assert target.read_text(encoding="utf-8") == "keep this"
