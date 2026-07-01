CREATE TABLE contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    primary_number TEXT NOT NULL UNIQUE,
    display_name TEXT,
    is_anonymous INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_contacts_display_name ON contacts (display_name);

CREATE TABLE phonebook_entries (
    phonebook_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    number_normalized TEXT NOT NULL,
    PRIMARY KEY (phonebook_id, number_normalized)
);

CREATE INDEX idx_phonebook_entries_number ON phonebook_entries (number_normalized);

CREATE TABLE calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id INTEGER NOT NULL REFERENCES contacts (id),
    call_type INTEGER NOT NULL,
    caller_number TEXT,
    called_number TEXT,
    port TEXT,
    device TEXT,
    call_date TEXT NOT NULL,
    duration_seconds INTEGER,
    raw_name TEXT
);

-- SQLite behandelt NULL in einem UNIQUE-Constraint als "nie gleich zu NULL", d.h. ein
-- table-level UNIQUE(...) mit nullable Spalten (caller_number/called_number/duration_seconds
-- sind es je nach Anruftyp) würde Duplikate NICHT verhindern. Daher Dedupe über einen
-- Ausdrucks-Index mit COALESCE auf feste Sentinel-Werte statt echter NULLs.
CREATE UNIQUE INDEX idx_calls_dedupe ON calls (
    call_date,
    COALESCE(caller_number, ''),
    COALESCE(called_number, ''),
    COALESCE(duration_seconds, -1)
);

CREATE INDEX idx_calls_contact_date ON calls (contact_id, call_date DESC);
CREATE INDEX idx_calls_date ON calls (call_date DESC);

CREATE TABLE sync_state (
    key TEXT PRIMARY KEY,
    value TEXT
);
