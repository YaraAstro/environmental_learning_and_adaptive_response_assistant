CREATE TABLE memories (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL CHECK (length(value) BETWEEN 1 AND 500),
    updated_at TEXT NOT NULL
);
