-- NetVote schema (SQLite). Foreign keys are enforced per-connection (PRAGMA foreign_keys=ON).
-- DATABASE CONCEPT: constraints (UNIQUE / CHECK / FK) are the last line of defence even if
-- application-level synchronisation had a bug.

CREATE TABLE IF NOT EXISTS voters (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    voter_id      TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    has_voted     INTEGER NOT NULL DEFAULT 0 CHECK (has_voted IN (0,1)),
    created_at    TEXT NOT NULL,
    last_login    TEXT,
    status        TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','suspended'))
);

CREATE TABLE IF NOT EXISTS admins (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    last_login    TEXT
);

CREATE TABLE IF NOT EXISTS candidates (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    party       TEXT NOT NULL,
    symbol      TEXT NOT NULL DEFAULT '*',
    color       TEXT NOT NULL DEFAULT '#2456e6',
    description TEXT NOT NULL DEFAULT '',
    vote_count  INTEGER NOT NULL DEFAULT 0 CHECK (vote_count >= 0),
    status      TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','withdrawn'))
);

-- Ballot secrecy: voter_ref is an HMAC pseudonym of the voter id (not the id itself).
-- vote_hash / prev_hash form a hash chain => tamper-EVIDENT ledger (not tamper-proof).
CREATE TABLE IF NOT EXISTS votes (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id TEXT NOT NULL UNIQUE,
    voter_ref      TEXT NOT NULL,
    candidate_id   INTEGER NOT NULL REFERENCES candidates(id),
    request_id     TEXT NOT NULL UNIQUE,        -- idempotency key
    timestamp      TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'confirmed',
    prev_hash      TEXT,
    vote_hash      TEXT
);
-- One vote per voter, enforced by the database itself.
CREATE UNIQUE INDEX IF NOT EXISTS ux_votes_voter ON votes(voter_ref);
CREATE INDEX IF NOT EXISTS ix_votes_candidate ON votes(candidate_id);

CREATE TABLE IF NOT EXISTS audit_logs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    TEXT,
    action     TEXT NOT NULL,
    request_id TEXT,
    ip_address TEXT,
    user_agent TEXT,
    timestamp  TEXT NOT NULL,
    details    TEXT,
    severity   TEXT NOT NULL DEFAULT 'INFO',
    status     TEXT NOT NULL DEFAULT 'OK'
);
CREATE INDEX IF NOT EXISTS ix_audit_action ON audit_logs(action);
CREATE INDEX IF NOT EXISTS ix_audit_time ON audit_logs(timestamp);
CREATE INDEX IF NOT EXISTS ix_audit_user ON audit_logs(user_id);

CREATE TABLE IF NOT EXISTS requests (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id         TEXT NOT NULL,
    request_type       TEXT NOT NULL,
    user_id            TEXT,
    status             TEXT NOT NULL,
    response_code      INTEGER,
    created_at         TEXT NOT NULL,
    completed_at       TEXT,
    processing_time_ms REAL,
    ip_address         TEXT
);
CREATE INDEX IF NOT EXISTS ix_requests_rid ON requests(request_id);
CREATE INDEX IF NOT EXISTS ix_requests_time ON requests(created_at);

CREATE TABLE IF NOT EXISTS system_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    severity   TEXT NOT NULL DEFAULT 'INFO',
    message    TEXT NOT NULL,
    timestamp  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_events_time ON system_events(timestamp);

CREATE TABLE IF NOT EXISTS election_config (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    election_name    TEXT NOT NULL,
    start_time       TEXT,
    end_time         TEXT,
    status           TEXT NOT NULL DEFAULT 'NOT_STARTED'
                     CHECK (status IN ('NOT_STARTED','ACTIVE','PAUSED','ENDED')),
    total_registered INTEGER NOT NULL DEFAULT 0,
    total_votes      INTEGER NOT NULL DEFAULT 0
);
