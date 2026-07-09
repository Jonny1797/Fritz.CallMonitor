-- "Ausblenden" (lokales, box-unabhängiges Verstecken) ist obsolet: die
-- Anrufbeantworter-Nachrichtenliste soll jetzt echtes Löschen (DeleteMessage) und
-- echten Sync (Pruning auf der Box gelöschter Nachrichten) nutzen statt eines
-- rein lokalen Zwischenzustands.
ALTER TABLE voicemail_messages DROP COLUMN is_hidden;
