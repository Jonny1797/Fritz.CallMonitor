-- Die Fritz!Box liefert Anrufe in GetCallList bereits korrekt chronologisch
-- sortiert (neueste zuerst) und mit einer pro Anruf ansteigenden Id, aber der
-- Date-Zeitstempel selbst hat nur Minutengenauigkeit (fritzconnection parst
-- ihn mit '%d.%m.%y %H:%M', keine Sekunden). Bei zwei Anrufen in derselben
-- Minute lieferte "ORDER BY call_date DESC" daher eine unbestimmte
-- Reihenfolge. box_call_id dient als Tiebreaker (hoehere Id = neuer, gegen
-- eine echte Fritz!Box empirisch verifiziert) - bewusst NICHT Teil des
-- Dedupe-Schluessels, da diese Id ueber lange Zeitraeume rotiert.
ALTER TABLE calls ADD COLUMN box_call_id INTEGER;
