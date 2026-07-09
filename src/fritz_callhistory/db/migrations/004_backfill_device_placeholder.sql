-- Die Fritz!Box sendet in <Device> den Literal-String "-1", wenn kein Gerät
-- zutrifft (z.B. abgelehnte/nicht angenommene Anrufe). Vor dem Fix in
-- sync/service.py landete dieser Rohwert unverändert in der DB und wurde in
-- der GUI als Text "-1" angezeigt. Bestehende Installationen bereinigen.
UPDATE calls SET device = NULL WHERE device = '-1';
