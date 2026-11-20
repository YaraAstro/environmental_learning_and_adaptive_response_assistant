"""A small offline CLI for validating the project foundation."""

import argparse
import asyncio
import json
import platform
import sqlite3
import sys
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import ValidationError

from elara import __version__
from elara.core.contracts import AgentRequest, ConversationTurn
from elara.core.conversation import ConversationService
from elara.core.identity import load_identity
from elara.core.sessions import SessionConflict, SessionNotFound
from elara.core.settings import Settings, load_settings
from elara.memory.database import backup_database
from elara.memory.store import SQLiteStore


def doctor(settings: Settings) -> int:
    baseline_ok = sys.version_info[:2] == (3, 12)
    with sqlite3.connect(":memory:") as connection:
        connection.execute("CREATE VIRTUAL TABLE probe USING fts5(body)")
        connection.execute("INSERT INTO probe(body) VALUES (?)", ("ELARA ready",))
        assert connection.execute(
            "SELECT body FROM probe WHERE probe MATCH 'ELARA'"
        ).fetchone() == ("ELARA ready",)
    # These imports intentionally verify the installed development stack.
    import pydantic_ai  # noqa: F401

    identity = load_identity()
    print(
        json.dumps(
            {
                "status": "ok" if baseline_ok else "python_baseline_mismatch",
                "elara": __version__,
                "python": platform.python_version(),
                "required_python": "3.12",
                "platform": sys.platform,
                "sqlite_fts5": "ok",
                "pydantic_ai": "import_ok",
                "identity_version": identity.version,
                "provider": settings.inference.provider,
                "network_requested": False,
                "persistent_data_written": False,
            },
            indent=2,
        )
    )
    return 0 if baseline_ok else 1


def database_path(settings: Settings) -> Path:
    return settings.data_dir / "database" / "elara.sqlite3"


def session_command(args: argparse.Namespace, settings: Settings) -> int:
    path = database_path(settings)
    if not path.is_file():
        if args.session_command == "list":
            print("[]")
            return 0
        raise SessionNotFound("No saved sessions")
    store = SQLiteStore(path)
    if args.session_command == "list":
        print(
            json.dumps(
                [session.model_dump(mode="json") for session in store.list_sessions()], indent=2
            )
        )
    elif args.session_command == "delete":
        store.delete_session(args.id)
        print("Session and transcript deleted. Action audit metadata and backups are retained.")
    elif args.session_command == "audit":
        print(
            json.dumps(
                [event.model_dump(mode="json") for event in store.audit_events(args.id)], indent=2
            )
        )
    else:
        snapshot = store.snapshot(args.id)
        content = snapshot.model_dump_json(indent=2)
        if args.session_command == "export":
            with args.output.open("x", encoding="utf-8") as handle:
                handle.write(content + "\n")
            print("Session exported.")
        else:
            print(content)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="elara", description="ELARA offline foundation")
    parser.add_argument("--version", action="version", version=f"ELARA {__version__}")
    parser.add_argument("--config", type=Path, help="Path to a validated TOML configuration")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Check Python, SQLite FTS5, identity, and AI imports")
    settings_command = commands.add_parser("settings", help="Inspect effective settings")
    settings_command.add_subparsers(dest="settings_command", required=True).add_parser("show")
    chat = commands.add_parser("chat", help="Run a clearly labelled offline simulation")
    chat.add_argument("message", nargs="?", help="One-shot message; omit for an interactive loop")
    persistence = chat.add_mutually_exclusive_group()
    persistence.add_argument("--save", action="store_true", help="Save a new local conversation")
    persistence.add_argument("--session", type=UUID, help="Resume an existing saved conversation")
    sessions = commands.add_parser("sessions", help="Manage saved local conversations")
    session_commands = sessions.add_subparsers(dest="session_command", required=True)
    session_commands.add_parser("list")
    for name in ("show", "export", "delete", "audit"):
        subcommand = session_commands.add_parser(name)
        subcommand.add_argument("id", type=UUID)
        if name == "export":
            subcommand.add_argument("--output", type=Path, required=True)
    database = commands.add_parser("database", help="Initialize or back up local storage")
    database_commands = database.add_subparsers(dest="database_command", required=True)
    database_commands.add_parser("init")
    backup = database_commands.add_parser("backup")
    backup.add_argument("output", type=Path, help="New backup file (never overwrites)")
    args = parser.parse_args(argv)
    try:
        settings = load_settings(args.config)
        if args.command == "doctor":
            return doctor(settings)
        if args.command == "settings":
            print(settings.model_dump_json(indent=2))
            return 0
        if args.command == "sessions":
            return session_command(args, settings)
        if args.command == "database":
            if args.database_command == "init":
                SQLiteStore(database_path(settings))
                print("Database schema is ready.")
            else:
                backup_database(database_path(settings), args.output)
                print("Database backup created.")
            return 0
        from elara.app import build_runtime

        runtime = build_runtime(settings)
        session_id = uuid4()
        conversation: ConversationService | None = None
        temporary_history: list[ConversationTurn] = []
        if args.save or args.session:
            path = database_path(settings)
            if args.session and not path.is_file():
                raise SessionNotFound("No saved sessions")
            store = SQLiteStore(path)
            if args.session:
                session_id = store.snapshot(args.session).session.id
            else:
                session_id = store.create_session().id
            conversation = ConversationService(runtime, store)
            print(f"Saved session: {session_id}")

        async def respond(message: str) -> None:
            if conversation is not None:
                result = await conversation.respond(session_id, message)
            else:
                result = await runtime.respond(
                    AgentRequest(
                        message=message, session_id=session_id, history=tuple(temporary_history)
                    )
                )
                temporary_history.extend(
                    [
                        ConversationTurn(role="user", content=message),
                        ConversationTurn(role="assistant", content=result.message),
                    ]
                )
            print(f"ELARA [simulation]: {result.message}")

        if args.message is not None:
            asyncio.run(respond(args.message))
        else:
            retention = "Saved locally." if conversation else "No conversation is saved."
            print(f"ELARA offline simulation. {retention} Type /exit to quit.")
            while True:
                message = input("You: ").strip()
                if message in {"/exit", "/quit"}:
                    break
                if message:
                    asyncio.run(respond(message))
        return 0
    except SessionNotFound:
        print("ELARA: session not found; use 'sessions list' to find saved IDs.", file=sys.stderr)
        return 1
    except SessionConflict:
        print("ELARA: session changed in another process; retry your message.", file=sys.stderr)
        return 1
    except FileExistsError:
        print("ELARA: output already exists; choose a new filename.", file=sys.stderr)
        return 1
    except (ValidationError, OSError, ValueError, sqlite3.Error) as exc:
        # Do not echo invalid config values, prompts, or provider credentials.
        print(f"ELARA: {type(exc).__name__}; check configuration or run doctor.", file=sys.stderr)
        return 1
    except (EOFError, KeyboardInterrupt):
        print("\nGoodbye.")
        return 0
