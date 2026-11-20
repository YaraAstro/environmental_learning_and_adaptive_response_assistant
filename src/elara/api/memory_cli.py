"""User-only memory controls, never dispatched from model output."""

import json
from pathlib import Path

from elara.memory.store import SQLiteStore


def memory_command(path: Path, operation: str, key: str = "", value: str = "") -> None:
    if operation == "set":
        fact = SQLiteStore(path).remember(key, value)
        print(f"Remembered {fact.key}: {fact.value}")
    elif operation == "list":
        facts = SQLiteStore(path).memories() if path.is_file() else ()
        print(json.dumps([fact.model_dump() for fact in facts], indent=2, ensure_ascii=False))
    elif operation == "forget":
        removed = path.is_file() and SQLiteStore(path).forget(key)
        print(
            "Memory deleted. Existing chats and backups are retained."
            if removed
            else "No memory with that key."
        )
    else:
        raise ValueError("Unknown memory command")


def interactive_command(message: str, path: Path) -> bool:
    if not message.startswith("/"):
        return False
    command, _, argument = message.partition(" ")
    if command == "/help":
        print("/remember key=value | /memories | /forget key | /help | /exit")
        print(
            "Memory: up to 20 facts, 500 characters each. Recall is local and shared across chats."
        )
    elif command in {"/memories", "/memory"}:
        memory_command(path, "list")
    elif command == "/remember":
        key, separator, value = argument.partition("=")
        if not separator:
            raise ValueError("Use /remember key=value")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        memory_command(path, "set", key.strip(), value)
    elif command == "/forget":
        if not argument.strip():
            raise ValueError("Use /forget key")
        memory_command(path, "forget", argument.strip())
    else:
        print("Unknown command. Type /help.")
    return True
