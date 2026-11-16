"""Live-Anrufe (vom CallMonitor verfolgte, noch nicht synchronisierte Anrufe) als eigener
Wert für "Alle Anrufe" - rein, ohne Widgets. Das Verfolgen (Verbindungs-id -> LiveCall)
bleibt in der Ansicht."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from fritz_callhistory.fritz.call_types import CallType
from fritz_callhistory.fritz.call_types import display as call_type_display
from fritz_callhistory.sync.caller_directory import CallerIdentity


class LiveCallState(Enum):
    RINGING = "ringing"
    CONNECTED = "connected"
    ENDED = "ended"


# Reihenfolge in der Spalte "Richtung": laufende zuerst, beendete zuletzt.
_STATE_ORDER = {
    LiveCallState.CONNECTED: 0,
    LiveCallState.RINGING: 1,
    LiveCallState.ENDED: 2,
}

_RUNNING_DISPLAY = {
    LiveCallState.RINGING: "🔔 Klingelt …",
    LiveCallState.CONNECTED: "📞 Verbunden …",
}


@dataclass
class LiveCall:
    caller_number: str
    called_number: str
    identity: CallerIdentity
    started_at: str  # ISO8601
    state: LiveCallState = LiveCallState.RINGING
    answered: bool = False  # war der Anruf je verbunden, auch nach dem Ende

    @property
    def ended_call_type(self) -> CallType:
        """Anzeige eines beendeten Anrufs (wie der echte Eintrag nach dem Sync): angenommene
        "Eingehend", nie angenommene "Verpasst". Der CallMonitor verfolgt nur eingehende."""
        return CallType.INCOMING if self.answered else CallType.MISSED

    # Gleiche Lesefelder wie CallRecord, damit "Alle Anrufe" Datum, Dauer und
    # Port/Gerät für beide Zeilenarten mit denselben Spalten anzeigt.
    @property
    def call_date(self) -> str:
        return self.started_at

    @property
    def duration_seconds(self) -> None:
        return None

    @property
    def port(self) -> None:
        return None

    @property
    def device(self) -> None:
        return None

    @property
    def direction_sort_key(self) -> tuple[int, int]:
        """Live-Anrufe sortieren vor allen Box-Codes (die als (1, call_type) sortieren)."""
        return (0, _STATE_ORDER[self.state])

    def display(self) -> str:
        """Icon und Label für die Spalte "Richtung"."""
        if self.state is LiveCallState.ENDED:
            return call_type_display(self.ended_call_type)
        return _RUNNING_DISPLAY[self.state]

    def is_new_missed(self, last_seen_at: str | None) -> bool:
        return (
            self.state is LiveCallState.ENDED
            and not self.answered
            and last_seen_at is not None
            and self.started_at > last_seen_at
        )
