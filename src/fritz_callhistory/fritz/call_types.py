"""Wissen über Anruftypen an einer Stelle: Box-Codes, Richtung, "verpasst", Gegenstellen-
Nummer, Labels und Icons. Rein und ohne fritzconnection-Import, damit sync/ und gui/ es
nutzen dürfen (wie fritz.exceptions).

Die DB speichert den rohen Box-Code; die Funktionen nehmen daher einfache ``int``-Codes
entgegen und werfen bei unbekannten Codes nicht."""

from __future__ import annotations

from enum import IntEnum


class CallType(IntEnum):
    INCOMING = 1
    MISSED = 2
    OUTGOING = 3
    ACTIVE_INCOMING = 9
    REJECTED = 10
    ACTIVE_OUTGOING = 11
    # Nur zur Anzeige für live per CallMonitor verfolgte Anrufe - werden nie gespeichert
    # und liegen bewusst ausserhalb des Wertebereichs echter Box-Codes.
    LIVE_RINGING = -1
    LIVE_CONNECTED = -2


_OUTGOING = (CallType.OUTGOING, CallType.ACTIVE_OUTGOING)

_LABELS = {
    CallType.INCOMING: "Eingehend",
    CallType.MISSED: "Verpasst",
    CallType.OUTGOING: "Ausgehend",
    CallType.ACTIVE_INCOMING: "Eingehend (aktiv)",
    CallType.REJECTED: "Abgelehnt",
    CallType.ACTIVE_OUTGOING: "Ausgehend (aktiv)",
    CallType.LIVE_RINGING: "Klingelt …",
    CallType.LIVE_CONNECTED: "Verbunden …",
}

_ICONS = {
    CallType.INCOMING: "↘",
    CallType.MISSED: "✕",
    CallType.OUTGOING: "↗",
    CallType.ACTIVE_INCOMING: "↘",
    CallType.REJECTED: "⊘",
    CallType.ACTIVE_OUTGOING: "↗",
    CallType.LIVE_RINGING: "🔔",
    CallType.LIVE_CONNECTED: "📞",
}


def is_outgoing(call_type: int) -> bool:
    return call_type in _OUTGOING


def is_missed(call_type: int) -> bool:
    """Nur Verpasst (2); Abgelehnt (10) zählt nicht als verpasster Anruf."""
    return call_type == CallType.MISSED


def counterparty_number(
    call_type: int, caller_number: str | None, called_number: str | None
) -> str | None:
    """Nummer der Gegenseite - bei ausgehenden Anrufen die angerufene, sonst die anrufende."""
    return called_number if is_outgoing(call_type) else caller_number


def label(call_type: int) -> str:
    return _LABELS.get(call_type, str(call_type))


def icon(call_type: int) -> str:
    return _ICONS.get(call_type, "")


def display(call_type: int) -> str:
    """Icon und Label für die Tabellenanzeige; unbekannte Codes als nackte Zahl."""
    symbol = icon(call_type)
    return f"{symbol} {label(call_type)}" if symbol else label(call_type)
