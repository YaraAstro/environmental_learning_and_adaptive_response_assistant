# Foundation architecture

The source of the plan is the existing ELARA Project Dossier in the adjacent
`../assets/ELARA_Project_Dossier` directory, especially the implementation guide,
project map, and environment setup. Those documents describe future capabilities;
this repository's README describes what actually exists.

| Package | Responsibility now |
| --- | --- |
| `core` | Settings, identity, conversation service, session and audit contracts |
| `actions` | Pure policy evaluator; audited gateway, scoped grants, workspace reads, attachment runtime |
| `api` | Explicit workspace CLI command wiring |
| `memory` | SQLite migrations, sessions, atomic exchanges, backups, audit storage |
| `inference` | Mock and local Ollama adapters, readiness checks, history translation |
| `observability` | Best-effort credential redaction before persistence |
| `app.py` | Dependency composition |
| `cli.py` | Diagnostics, saved/temporary chat, sessions, and database operations |

Reserved package boundaries: `context`, `cognition`, `verification`,
`platform`, and `knowledge`. They contain no implementation
until a milestone needs them. Core code depends only on Python/Pydantic and path
configuration utilities. Framework adapters depend on core contracts.

The gateway dispatches `demo.echo`, `workspace.read`, and `workspace.list`. A trusted
caller supplies grants bound to actor, session UUID, capability, and exact resource.
The workspace CLI creates a grant for one explicitly requested operation. Chat's
attachment wrapper grants only caller-selected reads per turn, then supplies typed
documents to Ollama as untrusted reference text. Model-selected tools remain disabled.
No model-facing grant creation, arbitrary callable dispatch, shell tools,
or network tools are exposed.

The gateway requires an `AuditSink`; use `SQLiteStore` for durable records and
an in-memory implementation for tests. Decisions and started events must be
recorded before dispatch. Core conversation code depends on a `SessionRepository`
protocol; the CLI supplies SQLite and keeps plain chat temporary unless opted in.

This proves denial-before-dispatch, not complete security. Before model tools:
implement authenticated scopes, immutable arguments, expiring authorizations,
race-resistant execution, and stronger adapter-level enforcement. Current path/link
checks assume a trusted folder; see ADR 0004 for workspace limits.
See ADR 0002 for persistence, audit retention, and recovery guarantees.
