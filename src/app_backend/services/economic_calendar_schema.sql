PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

INSERT OR IGNORE INTO schema_migrations (version) VALUES (1);

CREATE TABLE IF NOT EXISTS economic_calendar (
    id INTEGER PRIMARY KEY,
    event_key TEXT NOT NULL CHECK (event_key IN (
        'consumer_price_index',
        'employment_situation',
        'personal_income_and_outlays',
        'gross_domestic_product',
        'fomc_statement'
    )),
    event_name TEXT NOT NULL,
    release_date TEXT NOT NULL,
    release_time_et TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('BLS', 'BEA', 'Federal Reserve')),
    source_url TEXT NOT NULL,
    source_domain TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (event_key, release_date, release_time_et)
);

CREATE INDEX IF NOT EXISTS idx_economic_calendar_release_time
ON economic_calendar(release_date, release_time_et);

CREATE INDEX IF NOT EXISTS idx_economic_calendar_event_key_release
ON economic_calendar(event_key, release_date DESC);

CREATE INDEX IF NOT EXISTS idx_economic_calendar_source_release
ON economic_calendar(source, release_date);
