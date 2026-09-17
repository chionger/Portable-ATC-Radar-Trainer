CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY,
    checksum TEXT NOT NULL
);
CREATE TABLE events (
    event_id TEXT PRIMARY KEY NOT NULL,
    session_id TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK (sequence > 0),
    document TEXT NOT NULL,
    UNIQUE (session_id, sequence)
);
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY NOT NULL,
    source_sequence INTEGER NOT NULL,
    projection_version TEXT NOT NULL,
    document TEXT NOT NULL,
    FOREIGN KEY (session_id, source_sequence) REFERENCES events(session_id, sequence)
);
CREATE TABLE requests (
    session_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    first_sequence INTEGER NOT NULL,
    last_sequence INTEGER NOT NULL,
    PRIMARY KEY (session_id, idempotency_key),
    CHECK (first_sequence > 0 AND last_sequence >= first_sequence),
    FOREIGN KEY (session_id, first_sequence) REFERENCES events(session_id, sequence),
    FOREIGN KEY (session_id, last_sequence) REFERENCES events(session_id, sequence)
);
CREATE TABLE outbox (
    event_id TEXT PRIMARY KEY NOT NULL REFERENCES events(event_id),
    dispatched INTEGER NOT NULL DEFAULT 0 CHECK (dispatched IN (0, 1))
);
CREATE INDEX pending_outbox ON outbox(dispatched, event_id);
