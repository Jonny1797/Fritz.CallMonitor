-- Die Fritz!Box liefert Anrufe in GetCallList bereits korrekt chronologisch
-- sortiert (neueste zuerst) und mit einer pro Anruf ansteigenden Id, aber der
-- Date-Zeitstempel selbst hat nur Minutengenauigkeit (fritzconnection parst
-- ihn mit '%d.%m.%y %H:%M', keine Sekunden). Bei zwei Anrufen in derselben
-- Minute lieferte "ORDER BY call_date DESC" daher eine unbestimmte
-- Reihenfolge. box_call_id dient als Tiebreaker (höhere Id = neuer, gegen
-- eine echte Fritz!Box empirisch verifiziert) - bewusst NICHT Teil des
-- Dedupe-Schlüssels, da diese Id über lange Zeiträume rotiert.
ALTER TABLE calls ADD COLUMN box_call_id INTEGER;
