import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest

from elara.core.contracts import AgentRequest, AgentResponse
from elara.core.conversation import ConversationService
from elara.core.sessions import SessionConflict, SessionNotFound
from elara.memory import database
from elara.memory.database import SchemaError, backup_database, connect
from elara.memory.store import SQLiteStore


class RecordingRuntime:
    def __init__(self) -> None:
        self.requests: list[AgentRequest] = []

    async def respond(self, request: AgentRequest) -> AgentResponse:
        self.requests.append(request)
        return AgentResponse(message="Understood", session_id=request.session_id, simulated=True)


async def test_history_survives_reopening_and_reaches_runtime(tmp_path: Path) -> None:
    path = tmp_path / "elara.sqlite3"
    store = SQLiteStore(path)
    session = store.create_session()
    await ConversationService(RecordingRuntime(), store).respond(session.id, "Call me Alex")
    reopened = SQLiteStore(path)
    runtime = RecordingRuntime()
    await ConversationService(runtime, reopened).respond(session.id, "What is my name?")
    assert [turn.content for turn in runtime.requests[0].history] == ["Call me Alex", "Understood"]
    snapshot = reopened.snapshot(session.id)
    assert snapshot.session.revision == 2
    assert len(snapshot.turns) == 4
    assert snapshot.session.created_at.tzinfo is not None


async def test_failed_generation_saves_no_partial_exchange(tmp_path: Path) -> None:
    class FailedRuntime:
        async def respond(self, request: AgentRequest) -> AgentResponse:
            raise RuntimeError("provider failed")

    store = SQLiteStore(tmp_path / "elara.sqlite3")
    session = store.create_session()
    with pytest.raises(RuntimeError):
        await ConversationService(FailedRuntime(), store).respond(session.id, "Hello")
    assert store.snapshot(session.id).turns == ()
    assert store.snapshot(session.id).session.revision == 0


def test_failed_second_turn_rolls_back_first_turn_and_revision(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "elara.sqlite3")
    session = store.create_session()
    with connect(store.path) as connection:
        connection.execute("""CREATE TRIGGER reject_assistant BEFORE INSERT ON turns
            WHEN NEW.role = 'assistant' BEGIN SELECT RAISE(ABORT, 'injected failure'); END;""")
    with pytest.raises(sqlite3.IntegrityError):
        store.append_exchange(session.id, "hello", "reply", simulated=True, expected_revision=0)
    snapshot = store.snapshot(session.id)
    assert snapshot.turns == ()
    assert snapshot.session.revision == 0


def test_stale_exchange_cannot_overwrite_newer_history(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "elara.sqlite3")
    session = store.create_session()
    other = SQLiteStore(store.path)
    other.append_exchange(session.id, "first", "reply", simulated=True, expected_revision=0)
    with pytest.raises(SessionConflict):
        store.append_exchange(session.id, "stale", "reply", simulated=True, expected_revision=0)
    assert len(store.snapshot(session.id).turns) == 2


def test_migrations_are_idempotent_and_reject_future_schema(tmp_path: Path) -> None:
    path = tmp_path / "elara.sqlite3"
    SQLiteStore(path)
    SQLiteStore(path)
    with connect(path) as connection:
        assert connection.execute("SELECT count(*) FROM schema_migrations").fetchone()[0] == 2
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        connection.execute("PRAGMA user_version = 999")
    with pytest.raises(SchemaError):
        SQLiteStore(path)
    with connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 999


def test_migration_checksum_mismatch_is_rejected(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "elara.sqlite3")
    with connect(store.path) as connection:
        connection.execute("UPDATE schema_migrations SET checksum = 'changed'")
    with pytest.raises(SchemaError):
        SQLiteStore(store.path)


def test_unversioned_existing_database_is_not_repurposed(tmp_path: Path) -> None:
    path = tmp_path / "other.sqlite3"
    with connect(path) as connection:
        connection.execute("CREATE TABLE unrelated (value TEXT)")
    with pytest.raises(SchemaError):
        SQLiteStore(path)
    with connect(path) as connection:
        assert connection.execute("SELECT count(*) FROM unrelated").fetchone()[0] == 0


def test_backup_is_restorable_and_never_overwrites(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "elara.sqlite3")
    session = store.create_session()
    store.append_exchange(session.id, "hello", "reply", simulated=True, expected_revision=0)
    backup = tmp_path / "backup.sqlite3"
    # Keep an open connection so backup must include committed data from WAL as well.
    with connect(store.path):
        backup_database(store.path, backup)
    restored = SQLiteStore(backup)
    assert restored.snapshot(session.id) == store.snapshot(session.id)
    original = backup.read_bytes()
    with pytest.raises(FileExistsError):
        backup_database(store.path, backup)
    assert backup.read_bytes() == original


def test_delete_cascades_and_unknown_sessions_do_not_get_created(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "elara.sqlite3")
    session = store.create_session()
    store.append_exchange(session.id, "hello", "reply", simulated=True, expected_revision=0)
    store.delete_session(session.id)
    with pytest.raises(SessionNotFound):
        store.snapshot(session.id)
    with pytest.raises(SessionNotFound):
        store.append_exchange(uuid4(), "hello", "reply", simulated=True, expected_revision=0)
    with connect(store.path) as connection:
        assert connection.execute("SELECT count(*) FROM turns").fetchone()[0] == 0
    assert store.list_sessions() == ()


def test_common_credentials_are_redacted_before_storage(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "elara.sqlite3")
    session = store.create_session()
    secret = "sk-exampleNeverPersist123456"
    store.append_exchange(
        session.id,
        f"My key is {secret}",
        'password="secret-value"',
        simulated=True,
        expected_revision=0,
    )
    snapshot = store.snapshot(session.id)
    assert secret not in snapshot.model_dump_json()
    assert "secret-value" not in snapshot.model_dump_json()
    assert "[REDACTED]" in snapshot.turns[0].content
    assert secret.encode() not in store.path.read_bytes()


def test_failed_migration_rolls_back_schema_and_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "failed.sqlite3"
    monkeypatch.setattr(
        database,
        "statements",
        lambda sql: iter(["CREATE TABLE should_roll_back (value TEXT)", "THIS IS INVALID SQL"]),
    )
    with pytest.raises(sqlite3.OperationalError):
        SQLiteStore(path)
    with connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
        assert (
            connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
            == []
        )
