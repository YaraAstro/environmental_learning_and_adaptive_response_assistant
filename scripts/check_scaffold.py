"""Dependency-free integrity checks; this does not substitute for pytest or CI."""

import ast
import json
import sqlite3
import tomllib
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    sources = sorted((root / "src").rglob("*.py"))
    sources += sorted((root / "tests").rglob("*.py"))
    sources += sorted((root / "scripts").rglob("*.py"))
    for source in sources:
        tree = ast.parse(
            source.read_text(encoding="utf-8"), filename=str(source), feature_version=(3, 12)
        )
        if source.parent == root / "src/elara/core":
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    forbidden = ("pydantic_ai", "elara.inference", "elara.platform")
                    assert not module.startswith(forbidden)
    for path in (root / "pyproject.toml", root / "config/elara.example.toml",
                 root / "src/elara/core/identity.toml"):
        with path.open("rb") as handle:
            tomllib.load(handle)
    dataset = root / "evals/datasets/foundation.jsonl"
    cases = [json.loads(line) for line in dataset.read_text(encoding="utf-8").splitlines()]
    assert len({case["id"] for case in cases}) == len(cases)
    with sqlite3.connect(":memory:") as connection:
        connection.execute("CREATE VIRTUAL TABLE probe USING fts5(body)")
        connection.execute("INSERT INTO probe VALUES ('synthetic ELARA fixture')")
        assert connection.execute(
            "SELECT count(*) FROM probe WHERE probe MATCH 'ELARA'"
        ).fetchone() == (1,)
    print(f"PASS: {len(sources)} Python files parse; TOML and {len(cases)} eval cases validate.")
    print("PASS: host SQLite FTS5 insertion and retrieval.")
    print("These checks do not verify installed dependencies or Python 3.12 compatibility.")


if __name__ == "__main__":
    main()
