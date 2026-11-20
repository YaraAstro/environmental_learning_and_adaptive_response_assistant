# ADR 0002: Explicit local sessions and durable action audit

Status: implemented; validation results are recorded in the README.

## Decision

Persist conversations only when the user selects `chat --save` or resumes a
known session. The default chat stays temporary. Store sessions and turns in
SQLite under the configured data directory. Pass saved history through domain
contracts to the provider adapter; do not persist vendor SDK objects.

Write each user/assistant exchange and its revision in one transaction, only
after generation succeeds. Reject stale writes so concurrent conversations
cannot silently attach a reply generated from old history. A failed response
leaves no partial exchange. Failed calls are not silently retried.

Use packaged SQL migrations with checksums and schema version checks. Enable
foreign keys, WAL, and a busy timeout. Use standard-library SQLite for this small
CLI; aiosqlite remains available for a future async service. No new dependencies
are required.

ActionGateway requires an audit sink. Persist decision and started events before
execution. A failure to write either prevents dispatch. Record success/failure
afterward. An interrupted action or failed final audit write can leave only a
started event: the outcome is unknown and it is not automatically safe to retry.
The only supported action remains synthetic `demo.echo`.

## Privacy and retention

Redact common credential patterns before transcripts enter SQLite. This is best
effort, not a secret or personal-information guarantee. SQLite and backups are
unencrypted. Audit records contain UUIDs, constrained capability/reason fields,
timestamps, and a resource hash; they omit prompts, raw paths, and exception text.
Hashes of predictable resources do not make those resources anonymous.

Deleting a session cascades to its turns. Audit metadata is retained independently,
and exports/backups remain under the user's control. WAL cleanup and SQLite secure
delete reduce residual content but do not promise forensic erasure.

## Recovery and limits

Use SQLite's backup API for a consistent backup, including committed WAL data.
Exports and backups must use a new filename. Migrations are forward-only. To
roll back, stop all ELARA processes and restore a compatible backup into a new
data directory; avoid destructive reverse migrations.

Database triggers enforce append-only audit operations through ordinary SQL.
They are not tamper protection against an administrator who can alter the DB.
The CLI assumes a single trusted local OS user; session UUIDs are identifiers,
not authentication tokens. Live model/provider integration is the next increment.
