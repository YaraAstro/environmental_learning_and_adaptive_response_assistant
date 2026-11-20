"""SQLite lifecycle, atomic forward migrations, and consistent backups."""

import hashlib
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path

MIGRATIONS = ("001_sessions.sql", "002_memories.sql")
SCHEMA_VERSION = len(MIGRATIONS)


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
    migrations = [
        files("elara.memory.migrations").joinpath(name).read_text("utf-8") for name in MIGRATIONS
    ]
    checksums = [hashlib.sha256(sql.encode()).hexdigest() for sql in migrations]
    with connect(path) as connection:
        with transaction(connection):
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if not 0 <= version <= SCHEMA_VERSION:
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
            else:
                rows = connection.execute(
                    "SELECT version, checksum FROM schema_migrations ORDER BY version"
                ).fetchall()
                if [(row[0], row[1]) for row in rows] != list(
                    enumerate(checksums[:version], start=1)
                ):
                    raise SchemaError("Migration history does not match this application")
            for index in range(version, SCHEMA_VERSION):
                for statement in statements(migrations[index]):
                    connection.execute(statement)
                connection.execute(
                    "INSERT INTO schema_migrations VALUES (?, ?, ?)",
                    (index + 1, checksums[index], datetime.now(UTC).isoformat()),
                )
                connection.execute(f"PRAGMA user_version = {index + 1}")
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
