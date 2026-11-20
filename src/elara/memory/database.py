"""SQLite lifecycle, atomic forward migrations, and consistent backups."""

import hashlib
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path

SCHEMA_VERSION = 1


class SchemaError(ValueError):
    """The database cannot be used with this application schema."""


def statements(sql: str) -> Iterator[str]:
    """Keep trigger bodies intact; executescript would implicitly commit a transaction."""
    buffer = ""
    for line in sql.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            yield buffer
            buffer = ""
    if buffer.strip():
        raise SchemaError("Incomplete migration statement")


@contextmanager
def connect(path: Path) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(path, timeout=5, isolation_level=None)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA secure_delete = ON")
        yield connection
    finally:
        connection.close()


@contextmanager
def transaction(connection: sqlite3.Connection) -> Iterator[None]:
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield
        connection.execute("COMMIT")
    except BaseException:
        connection.execute("ROLLBACK")
        raise


def migrate(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sql = files("elara.memory.migrations").joinpath("001_sessions.sql").read_text("utf-8")
    digest = hashlib.sha256(sql.encode()).hexdigest()
    with connect(path) as connection:
        with transaction(connection):
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if version not in (0, SCHEMA_VERSION):
                raise SchemaError("Unsupported schema version; restore a compatible backup")
            if version == 0:
                existing = connection.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
                ).fetchall()
                if existing:
                    raise SchemaError("Refusing to initialize an unversioned nonempty database")
                connection.execute(
                    "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, "
                    "checksum TEXT NOT NULL, applied_at TEXT NOT NULL)"
                )
                for statement in statements(sql):
                    connection.execute(statement)
                connection.execute(
                    "INSERT INTO schema_migrations VALUES (?, ?, ?)",
                    (SCHEMA_VERSION, digest, datetime.now(UTC).isoformat()),
                )
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            else:
                rows = connection.execute(
                    "SELECT version, checksum FROM schema_migrations ORDER BY version"
                ).fetchall()
                if [(row[0], row[1]) for row in rows] != [(SCHEMA_VERSION, digest)]:
                    raise SchemaError("Migration history does not match this application")
        connection.execute("PRAGMA journal_mode = WAL")


def backup_database(source: Path, destination: Path) -> None:
    """Include committed WAL contents. Refuse to overwrite any existing destination."""
    if not source.is_file():
        raise FileNotFoundError(source)
    # Exclusive creation ensures failures cannot delete or overwrite a pre-existing file.
    with destination.open("xb"):
        pass
    try:
        with (
            closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as reader,
            closing(sqlite3.connect(destination)) as writer,
        ):
            reader.backup(writer)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
