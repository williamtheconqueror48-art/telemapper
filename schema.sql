-- TELEMAPPER Postgres schema (Neon).
-- Forensic fields mirror the SQLite ForensicLedger: SHA256 per signal,
-- IST timestamps. Full raw HTML payloads stay OUT of Postgres (too heavy);
-- message text plus its hash is what gets stored.

CREATE TABLE IF NOT EXISTS searches (
    id SERIAL PRIMARY KEY,
    query TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    result_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'running'
);

CREATE TABLE IF NOT EXISTS signals (
    id SERIAL PRIMARY KEY,
    search_id INTEGER NOT NULL REFERENCES searches(id) ON DELETE CASCADE,
    channel TEXT NOT NULL,
    message_id TEXT,
    text TEXT,
    forward_source TEXT,
    url TEXT,
    sha256 TEXT NOT NULL,
    sealed_at_ist TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_signals_search ON signals(search_id);

CREATE TABLE IF NOT EXISTS discovered_channels (
    id SERIAL PRIMARY KEY,
    search_id INTEGER REFERENCES searches(id) ON DELETE CASCADE,
    channel TEXT NOT NULL,
    discovery_method TEXT,
    reason TEXT,
    hop_distance INTEGER,
    status TEXT,
    discovered_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_discovered_search ON discovered_channels(search_id);
