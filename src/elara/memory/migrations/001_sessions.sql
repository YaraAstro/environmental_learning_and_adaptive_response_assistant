CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 0 CHECK (revision >= 0)
);

CREATE TABLE turns (
    id INTEGER PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL CHECK (sequence > 0),
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    simulated INTEGER NOT NULL CHECK (simulated IN (0, 1)),
    created_at TEXT NOT NULL,
    UNIQUE (session_id, sequence)
);

CREATE TABLE audit_events (
    sequence INTEGER PRIMARY KEY,
    id TEXT NOT NULL UNIQUE,
    session_id TEXT NOT NULL,
    event_json TEXT NOT NULL
);

CREATE INDEX audit_events_session ON audit_events(session_id, sequence);

CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit_events
BEGIN
    SELECT RAISE(ABORT, 'Audit events cannot be updated');
END;

CREATE TRIGGER audit_no_delete BEFORE DELETE ON audit_events
BEGIN
    SELECT RAISE(ABORT, 'Audit events cannot be deleted');
END;
