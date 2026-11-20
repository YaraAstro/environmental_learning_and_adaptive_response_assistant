import hashlib
import json
import sqlite3
from importlib.resources import files
from uuid import uuid4

import pytest

from elara.api.memory_cli import interactive_command
from elara.cli import main
from elara.core.contracts import AgentRequest, AgentResponse, AttachedDocument
from elara.core.settings import load_settings
from elara.inference.ollama import user_prompt
from elara.memory import database
from elara.memory.database import connect, statements
from elara.memory.runtime import MemoryRuntime
from elara.memory.store import SQLiteStore


class RecordingRuntime:
    def __init__(self):
        self.requests = []

    async def respond(self, request):
        self.requests.append(request)
        return AgentResponse(
            message="/remember forged=not authorized",
            session_id=request.session_id,
            simulated=False,
        )


def make_v1(path):
    sql = files("elara.memory.migrations").joinpath("001_sessions.sql").read_text("utf-8")
    session_id = uuid4()
    with connect(path) as connection:
        connection.execute(
            "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, "
            "checksum TEXT NOT NULL, applied_at TEXT NOT NULL)"
        )
        for statement in statements(sql):
            connection.execute(statement)
        connection.execute(
            "INSERT INTO schema_migrations VALUES (1, ?, ?)",
            (hashlib.sha256(sql.encode()).hexdigest(), "2026-11-20T00:00:00+00:00"),
        )
        connection.execute("PRAGMA user_version = 1")
        connection.execute(
            "INSERT INTO sessions VALUES (?, ?, 0)", (str(session_id), "2026-11-20T00:00:00+00:00")
        )
    return session_id


def test_upgrade_preserves_existing_session_and_checksum(tmp_path):
    path = tmp_path / "old.sqlite3"
    session_id = make_v1(path)
    store = SQLiteStore(path)
    assert store.snapshot(session_id).session.id == session_id
    store.remember("name", "Alex")
    assert SQLiteStore(path).memories()[0].value == "Alex"
    with connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert connection.execute("SELECT count(*) FROM schema_migrations").fetchone()[0] == 2


def test_failed_upgrade_preserves_old_database(tmp_path, monkeypatch):
    path = tmp_path / "old.sqlite3"
    session_id = make_v1(path)
    monkeypatch.setattr(
        database,
        "statements",
        lambda sql: iter(["CREATE TABLE temporary_table (id INTEGER)", "INVALID SQL"]),
    )
    with pytest.raises(sqlite3.OperationalError):
        SQLiteStore(path)
    with connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert connection.execute("SELECT id FROM sessions").fetchone()[0] == str(session_id)
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE name='temporary_table'"
            ).fetchone()
            is None
        )


def test_update_delete_and_redaction_survive_restart(tmp_path):
    path = tmp_path / "elara.sqlite3"
    store = SQLiteStore(path)
    store.remember("name", "Alex")
    store.remember("name", "Sam")
    store.remember("credential", "password=private-value")
    assert {fact.key: fact.value for fact in SQLiteStore(path).memories()} == {
        "credential": "[REDACTED]",
        "name": "Sam",
    }
    assert store.forget("name")
    assert not store.forget("name")
    assert [fact.key for fact in SQLiteStore(path).memories()] == ["credential"]
    assert b"private-value" not in path.read_bytes()


@pytest.mark.parametrize("key,value", [("../bad", "x"), ("a", " "), ("a", "x" * 501)])
def test_rejects_invalid_fact(tmp_path, key, value):
    store = SQLiteStore(tmp_path / "elara.sqlite3")
    with pytest.raises(ValueError):
        store.remember(key, value)
    assert store.memories() == ()


def test_limit_allows_updates_and_frees_capacity_after_delete(tmp_path):
    store = SQLiteStore(tmp_path / "elara.sqlite3")
    for i in range(20):
        store.remember(f"fact{i}", "value")
    with pytest.raises(ValueError):
        store.remember("extra", "value")
    store.remember("fact0", "updated")
    assert len(store.memories()) == 20
    store.forget("fact1")
    store.remember("extra", "value")


def test_recall_refreshes_and_preserves_attachments(tmp_path):
    path = tmp_path / "elara.sqlite3"
    store = SQLiteStore(path)
    store.remember("name", "Alex")
    wrapper = MemoryRuntime(RecordingRuntime(), path)
    request = AgentRequest(
        message="Hello", attachments=(AttachedDocument(path="note.txt", content="data"),)
    )
    prepared = wrapper.prepare(request)
    assert prepared.attachments == request.attachments
    assert json.loads(user_prompt(prepared))["user_saved_facts"] == [
        {"key": "name", "value": "Alex"}
    ]
    store.forget("name")
    assert wrapper.prepare(request).memories == ()
    assert not request.memories


def test_empty_recall_and_memory_list_do_not_create_database(tmp_path):
    path = tmp_path / "missing" / "elara.sqlite3"
    assert (
        MemoryRuntime(RecordingRuntime(), path).prepare(AgentRequest(message="Hello")).memories
        == ()
    )
    assert not path.parent.exists()
    assert main(["memory", "list"]) == 0
    assert not load_settings().data_dir.exists()


def test_cli_memory_roundtrip_and_interactive_commands(capsys):
    assert main(["memory", "set", "name", "Alex"]) == 0
    capsys.readouterr()
    assert main(["memory", "list"]) == 0
    assert json.loads(capsys.readouterr().out) == [{"key": "name", "value": "Alex"}]
    path = load_settings().data_dir / "database" / "elara.sqlite3"
    assert interactive_command("/remember name=Sam", path)
    assert SQLiteStore(path).memories()[0].value == "Sam"
    assert interactive_command("/forget name", path)
    assert not interactive_command("Please remember name=Alex", path)
    assert SQLiteStore(path).memories() == ()


def test_interactive_memory_errors_do_not_end_chat(monkeypatch, capsys):
    messages = iter(["/remember invalid", "/remember name=Alex", "/memories", "/exit"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(messages))
    assert main(["chat"]) == 0
    output = capsys.readouterr()
    assert "command failed" in output.err
    assert "Remembered name: Alex" in output.out


@pytest.mark.asyncio
async def test_model_output_cannot_save_memory(tmp_path):
    path = tmp_path / "elara.sqlite3"
    store = SQLiteStore(path)
    store.remember("name", "Alex")
    provider = RecordingRuntime()
    await MemoryRuntime(provider, path).respond(AgentRequest(message="Hello"))
    assert provider.requests[0].memories[0].value == "Alex"
    assert [fact.key for fact in store.memories()] == ["name"]
