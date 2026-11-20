"""A small offline CLI for validating the project foundation."""

import argparse
import asyncio
import json
import platform
import sqlite3
import sys
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from elara import __version__
from elara.core.contracts import AgentRequest
from elara.core.identity import load_identity
from elara.core.settings import Settings, load_settings


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
    print(json.dumps({
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
    }, indent=2))
    return 0 if baseline_ok else 1


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
    args = parser.parse_args(argv)
    try:
        settings = load_settings(args.config)
        if args.command == "doctor":
            return doctor(settings)
        if args.command == "settings":
            print(settings.model_dump_json(indent=2))
            return 0
        from elara.app import build_runtime

        runtime = build_runtime(settings)
        session_id = uuid4()

        async def respond(message: str) -> None:
            result = await runtime.respond(AgentRequest(message=message, session_id=session_id))
            print(f"ELARA [simulation]: {result.message}")

        if args.message is not None:
            asyncio.run(respond(args.message))
        else:
            print("ELARA offline simulation. No conversation is saved. Type /exit to quit.")
            while True:
                message = input("You: ").strip()
                if message in {"/exit", "/quit"}:
                    break
                if message:
                    asyncio.run(respond(message))
        return 0
    except (ValidationError, OSError, ValueError, sqlite3.Error) as exc:
        # Do not echo invalid config values, prompts, or provider credentials.
        print(f"ELARA: {type(exc).__name__}; check configuration or run doctor.", file=sys.stderr)
        return 1
    except (EOFError, KeyboardInterrupt):
        print("\nGoodbye.")
        return 0
