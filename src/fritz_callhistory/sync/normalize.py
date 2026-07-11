"""Rufnummern-Normalisierung als Kontakt-Gruppierungsschlüssel."""

from __future__ import annotations

import phonenumbers

ANONYMOUS_NUMBER = "anonymous"


def normalize_number(raw: str | None, region: str = "DE") -> tuple[str, bool]:
    """Normalisiert eine Rufnummer für den Kontakt-Gruppierungsschlüssel.

    Gibt (normalisierte_nummer, is_anonymous) zurück. Bei unterdrückter oder
    fehlender Nummer wird ein fester Platzhalter verwendet, damit solche Anrufe
    konsistent unter einem "Anonym"-Kontakt landen statt Duplikate zu erzeugen.
    """
    if not raw or not raw.strip():
        return ANONYMOUS_NUMBER, True

    raw = raw.strip()
    try:
        parsed = phonenumbers.parse(raw, region)
        if not phonenumbers.is_possible_number(parsed):
            raise phonenumbers.NumberParseException(
                phonenumbers.NumberParseException.NOT_A_NUMBER, "not possible"
            )
    except phonenumbers.NumberParseException:
        fallback = _fallback(raw)
        return fallback, fallback == ANONYMOUS_NUMBER

    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164), False


def _fallback(raw: str) -> str:
    """Best-effort Normalisierung für Nummern, die phonenumbers nicht parsen kann
    (z.B. interne Durchwahlen, Kurzwahlen, Notrufnummern)."""
    digits = "".join(ch for ch in raw if ch.isdigit() or ch == "+")
    return digits or ANONYMOUS_NUMBER


def format_number_display(number: str | None, region: str = "DE") -> str | None:
    """Menschenlesbar formatierte Darstellung einer Rufnummer (libphonenumber-
    Ländermetadaten, z.B. "+49 176 12345678") - NUR fürs Anzeigen. Niemals für
    Wahlvorgänge, DB-Vergleiche/Suche oder Sortierschlüssel verwenden, dafür
    weiterhin die unformatierte/normalisierte Nummer."""
    if not number or number == ANONYMOUS_NUMBER:
        return number
    try:
        parsed = phonenumbers.parse(number, region)
    except phonenumbers.NumberParseException:
        return number
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
