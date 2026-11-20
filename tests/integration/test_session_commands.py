import json
from pathlib import Path

import pytest

from elara.cli import database_path, main
from elara.core.settings import load_settings
from elara.memory.store import SQLiteStore


def test_session_cli_lifecycle_without_model_calls(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["database", "init"]) == 0
    store = SQLiteStore(database_path(load_settings()))
    session = store.create_session()
    store.append_exchange(
        session.id, "synthetic input", "reply", simulated=True, expected_revision=0
    )
    capsys.readouterr()
    session_id = str(session.id)
    assert main(["sessions", "list"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["id"] == session_id
    assert main(["sessions", "show", session_id]) == 0
    snapshot = json.loads(capsys.readouterr().out)
    export = tmp_path / "export.json"
    assert main(["sessions", "export", session_id, "--output", str(export)]) == 0
    assert json.loads(export.read_text(encoding="utf-8")) == snapshot
    assert main(["sessions", "export", session_id, "--output", str(export)]) == 1
    assert json.loads(export.read_text(encoding="utf-8")) == snapshot
    backup = tmp_path / "backup.sqlite3"
    assert main(["database", "backup", str(backup)]) == 0
    assert main(["database", "backup", str(backup)]) == 1
    assert main(["sessions", "delete", session_id]) == 0
    assert store.list_sessions() == ()
    assert SQLiteStore(backup).snapshot(session.id).session.revision == 1


def test_listing_sessions_does_not_create_storage(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["sessions", "list"]) == 0
    assert json.loads(capsys.readouterr().out) == []
    assert not load_settings().data_dir.exists()
