"""Canonical local sessions and append-only action audit records."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from elara.core.audit import AuditEvent
from elara.core.contracts import ConversationTurn, MemoryFact
from elara.core.sessions import Session, SessionConflict, SessionNotFound, SessionSnapshot
from elara.memory.database import connect, migrate, transaction
from elara.observability.redaction import redact_credentials


class SQLiteStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        migrate(path)

    def remember(self, key: str, value: str) -> MemoryFact:
        fact = MemoryFact(key=key, value=redact_credentials(value.strip()))
        with connect(self.path) as connection, transaction(connection):
            exists = connection.execute("SELECT 1 FROM memories WHERE key = ?", (key,)).fetchone()
            count = connection.execute("SELECT count(*) FROM memories").fetchone()[0]
            if not exists and count >= 20:
                raise ValueError("Memory is limited to 20 facts; forget one before adding more")
            connection.execute(
                "INSERT INTO memories (key, value, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
                "updated_at=excluded.updated_at",
                (fact.key, fact.value, datetime.now(UTC).isoformat()),
            )
        return fact

    def memories(self) -> tuple[MemoryFact, ...]:
        with connect(self.path) as connection:
            rows = connection.execute("SELECT key, value FROM memories ORDER BY key").fetchall()
        return tuple(MemoryFact.model_validate(dict(row)) for row in rows)

    def forget(self, key: str) -> bool:
        with connect(self.path) as connection:
            deleted = connection.execute("DELETE FROM memories WHERE key = ?", (key,)).rowcount
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        return deleted == 1

    def create_session(self) -> Session:
        session = Session(id=uuid4(), created_at=datetime.now(UTC))
        with connect(self.path) as connection:
            connection.execute(
                "INSERT INTO sessions (id, created_at) VALUES (?, ?)",
                (str(session.id), session.created_at.isoformat()),
            )
        return session

    def list_sessions(self) -> tuple[Session, ...]:
        with connect(self.path) as connection:
            rows = connection.execute(
                "SELECT * FROM sessions ORDER BY created_at DESC, id"
            ).fetchall()
        return tuple(Session.model_validate(dict(row)) for row in rows)

    def snapshot(self, session_id: UUID) -> SessionSnapshot:
        with connect(self.path) as connection:
            # One consistent snapshot of the revision and its turns, including concurrent writers.
            connection.execute("BEGIN")
            row = connection.execute(
                "SELECT * FROM sessions WHERE id = ?", (str(session_id),)
            ).fetchone()
            if row is None:
                raise SessionNotFound(str(session_id))
            turns = connection.execute(
                "SELECT role, content FROM turns WHERE session_id = ? ORDER BY sequence",
                (str(session_id),),
            ).fetchall()
            connection.execute("COMMIT")
        return SessionSnapshot(
            session=Session.model_validate(dict(row)),
            turns=tuple(ConversationTurn.model_validate(dict(turn)) for turn in turns),
        )

    def append_exchange(
        self,
        session_id: UUID,
        user_message: str,
        assistant_message: str,
        *,
        simulated: bool,
        expected_revision: int,
    ) -> None:
        timestamp = datetime.now(UTC).isoformat()
        with connect(self.path) as connection, transaction(connection):
            row = connection.execute(
                "SELECT revision FROM sessions WHERE id = ?", (str(session_id),)
            ).fetchone()
            if row is None:
                raise SessionNotFound(str(session_id))
            if row[0] != expected_revision:
                raise SessionConflict("Session changed; retry with current history")
            for offset, role, content in (
                (1, "user", user_message),
                (2, "assistant", assistant_message),
            ):
                connection.execute(
                    "INSERT INTO turns "
                    "(session_id, sequence, role, content, simulated, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        str(session_id),
                        expected_revision * 2 + offset,
                        role,
                        redact_credentials(content),
                        int(simulated),
                        timestamp,
                    ),
                )
            connection.execute(
                "UPDATE sessions SET revision = revision + 1 WHERE id = ?", (str(session_id),)
            )

    def delete_session(self, session_id: UUID) -> None:
        with connect(self.path) as connection, transaction(connection):
            result = connection.execute("DELETE FROM sessions WHERE id = ?", (str(session_id),))
            if result.rowcount != 1:
                raise SessionNotFound(str(session_id))
        # Best effort WAL cleanup; not a guarantee of forensic erasure on disk or in backups.
        with connect(self.path) as connection:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def record(self, event: AuditEvent) -> None:
        with connect(self.path) as connection:
            connection.execute(
                "INSERT INTO audit_events (id, session_id, event_json) VALUES (?, ?, ?)",
                (str(event.id), str(event.session_id), event.model_dump_json()),
            )

    def audit_events(self, session_id: UUID) -> tuple[AuditEvent, ...]:
        with connect(self.path) as connection:
            rows = connection.execute(
                "SELECT event_json FROM audit_events WHERE session_id = ? ORDER BY sequence",
                (str(session_id),),
            ).fetchall()
        return tuple(AuditEvent.model_validate_json(row[0]) for row in rows)
