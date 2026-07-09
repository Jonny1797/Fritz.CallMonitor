-- "Ausblenden" (lokales, box-unabhaengiges Verstecken) ist obsolet: die
-- Anrufbeantworter-Nachrichtenliste soll jetzt echtes Loeschen (DeleteMessage) und
-- echten Sync (Pruning auf der Box geloeschter Nachrichten) nutzen statt eines
-- rein lokalen Zwischenzustands.
ALTER TABLE voicemail_messages DROP COLUMN is_hidden;
