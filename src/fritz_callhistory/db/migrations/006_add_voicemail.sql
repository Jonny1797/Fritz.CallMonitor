CREATE TABLE voicemail_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tam_index INTEGER NOT NULL,
    box_path TEXT NOT NULL,
    caller_number TEXT,
    called_number TEXT,
    message_date TEXT NOT NULL,
    duration_seconds INTEGER,
    raw_name TEXT,
    is_new INTEGER NOT NULL DEFAULT 0,
    is_hidden INTEGER NOT NULL DEFAULT 0
);

-- box_path allein reicht als Dedupe-Key nicht sicher aus: die Box nummeriert
-- Aufnahmedateien pro Slot durch (z.B. "rec.0.000") und kann einen Pfad nach dem
-- Loeschen der zugehoerigen Nachricht fuer eine spaetere, voellig andere Nachricht
-- wiederverwenden. message_date zusaetzlich in den Dedupe-Key aufzunehmen macht eine
-- faelschliche Dedupe-Kollision praktisch ausgeschlossen (zwei verschiedene
-- Nachrichten muessten exakt denselben Pfad UND dieselbe Minute treffen).
CREATE UNIQUE INDEX idx_voicemail_dedupe ON voicemail_messages (tam_index, box_path, message_date);

CREATE INDEX idx_voicemail_date ON voicemail_messages (message_date DESC);
