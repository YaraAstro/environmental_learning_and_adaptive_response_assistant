# ADR 0001: Bootstrap an offline modular Python foundation

Status: implemented scaffold; dependency verification pending network access.

## Context

The workspace was empty. The existing dossier specifies Python 3.12, uv,
Pydantic AI, SQLite/FTS5, Windows-first operation, and CLI-first development.
It puts authorization tests before real tool access.

## Decision

Use a single package with domain contracts, a pure deny-by-default policy,
and a mock Pydantic AI runtime. Implement only settings that have real behavior.
Keep FastAPI/uvicorn in the `api` extra; no HTTP listener is needed yet.
Package identity as TOML rather than YAML, allowing standard-library parsing
and access from an installed wheel without repository-relative paths.

Keep live provider selection for the next increment. No provider credentials
were supplied and no model/backend has been verified. Mock mode is explicitly
labelled and cannot silently switch to a paid or remote provider.

## Consequences

The foundation can be tested without keys once dependencies are installed.
No claim of persistent memory, real assistance, or learning is made yet.
The dependency ranges in pyproject are provisional until resolution and checks
produce a tested lockfile. CI resolves once if that file is absent and enforces
locked installs when it is present.

## Reconsideration

Add real providers and persistent sessions after migrations, audit, and tool
authorization contracts are implemented and tested. Expand configuration only
alongside actual enforcement. Remove the initial unlocked CI path after the
first verified lockfile is committed.
