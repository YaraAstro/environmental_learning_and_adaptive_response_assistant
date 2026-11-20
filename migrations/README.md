# Persistence migrations

Executable migrations live in `src/elara/memory/migrations/` so installed wheels
carry their own schema. `001_sessions.sql` creates sessions, turns, and action
audits. `002_memories.sql` adds explicitly saved facts. The runner validates all
applied checksums before upgrading v1 to v2; existing sessions and audit rows are
preserved. The migrator stores a checksum and timestamp in `schema_migrations` and
advances `PRAGMA user_version` in the same transaction as the schema changes.

Migrations are forward-only. Never edit an applied migration: add a new version
and extend the runner with upgrade and failure-path tests. Back up before future
upgrades. Unknown versions, changed checksums, and unrelated databases are rejected.

Use `elara database backup NEW_PATH`. For rollback, stop all ELARA processes and
copy a compatible backup into a fresh data directory as `database/elara.sqlite3`;
point an explicit configuration at that directory. This avoids mixing a restored
database with stale WAL/SHM files from a newer one. Do not copy an active database
file directly; the SQLite backup API includes committed WAL contents.
