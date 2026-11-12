CREATE TABLE administrators (
    username TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE sessions (
    token_hash TEXT PRIMARY KEY,
    username TEXT NOT NULL REFERENCES administrators(username) ON DELETE CASCADE,
    csrf_token TEXT NOT NULL,
    expires_at REAL NOT NULL
);
CREATE TABLE login_failures (occurred_at REAL NOT NULL);
CREATE TABLE users (
    subject_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    level INTEGER NOT NULL CHECK (level IN (1,2,3)),
    active INTEGER NOT NULL CHECK (active IN (0,1)),
    consent_at TEXT,
    consent_version TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE user_divisions (
    subject_id TEXT NOT NULL REFERENCES users(subject_id) ON DELETE CASCADE,
    division TEXT NOT NULL,
    PRIMARY KEY(subject_id, division)
);
CREATE TABLE biometric_references (
    subject_id TEXT PRIMARY KEY REFERENCES users(subject_id) ON DELETE CASCADE,
    model_id TEXT NOT NULL,
    encrypted_samples BLOB NOT NULL,
    sample_count INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at TEXT NOT NULL,
    subject_id TEXT REFERENCES users(subject_id) ON DELETE SET NULL,
    requested_level INTEGER NOT NULL CHECK(requested_level IN (1,2,3)),
    division TEXT,
    granted INTEGER NOT NULL CHECK(granted IN (0,1)),
    reason TEXT NOT NULL,
    similarity REAL,
    margin REAL,
    elapsed_ms REAL NOT NULL,
    model_id TEXT NOT NULL,
    config_json TEXT NOT NULL
);
CREATE INDEX attempts_time ON attempts(id DESC);
CREATE INDEX sessions_expiry ON sessions(expires_at);
PRAGMA user_version=1;
