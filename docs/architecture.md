# Foundation architecture

The source of the plan is the existing ELARA Project Dossier in the adjacent
`../assets/ELARA_Project_Dossier` directory, especially the implementation guide,
project map, and environment setup. Those documents describe future capabilities;
this repository's README describes what actually exists.

| Package | Responsibility now |
| --- | --- |
| `core` | Settings, identity, conversation service, session and audit contracts |
| `actions` | Pure policy evaluator; audited synthetic gateway and scoped grants |
| `memory` | SQLite migrations, sessions, atomic exchanges, backups, audit storage |
| `inference` | Offline Pydantic AI adapter, including history translation |
| `observability` | Best-effort credential redaction before persistence |
| `app.py` | Dependency composition |
| `cli.py` | Diagnostics, saved/temporary chat, sessions, and database operations |

Reserved package boundaries: `context`, `cognition`, `verification`,
`platform`, `knowledge`, and `api`. They contain no implementation
until a milestone needs them. Core code depends only on Python/Pydantic and path
configuration utilities. Framework adapters depend on core contracts.

The initial gateway only dispatches `demo.echo` against `synthetic`. A trusted
caller supplies grants bound to actor and session UUIDs. Every other action and
resource is denied. No model-facing grant creation, arbitrary callable dispatch,
OS reads, shell tools, or network tools are exposed.

The gateway requires an `AuditSink`; use `SQLiteStore` for durable records and
an in-memory implementation for tests. Decisions and started events must be
recorded before dispatch. Core conversation code depends on a `SessionRepository`
protocol; the CLI supplies SQLite and keeps plain chat temporary unless opted in.

This proves denial-before-dispatch, not complete security. Before real tools:
implement authenticated scopes, immutable arguments, expiring authorizations,
path/link checks, race-resistant execution, and adapter-level enforcement.
See ADR 0002 for persistence, audit retention, and recovery guarantees.
