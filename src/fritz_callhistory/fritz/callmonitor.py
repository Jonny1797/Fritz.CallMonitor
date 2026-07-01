"""Client für den Fritz!Box CallMonitor (Port 1012).

Separates Feature, unabhängig von TR-064/fritzconnection: ein einfaches
Text-Protokoll über eine rohe TCP-Verbindung, das Ereignisse wie RING/CALL/
CONNECT/DISCONNECT streamt. Muss auf der Box einmalig per Wählcode #96*5* von
einem angeschlossenen Telefon aus aktiviert werden - ohne das schlägt der
Verbindungsaufbau fehl (Connection refused), auch wenn TR-064 einwandfrei
funktioniert.
"""

from __future__ import annotations

import socket
from collections.abc import Iterator
from dataclasses import dataclass

CALL_MONITOR_PORT = 1012
_CONNECT_TIMEOUT_SECONDS = 5.0


@dataclass
class RingEvent:
    caller_number: str
    called_number: str
    device: str


def parse_ring_event(line: str) -> RingEvent | None:
    """Parst eine CallMonitor-Zeile, falls es sich um ein RING-Ereignis handelt.

    Zeilenformat: "<Datum>;RING;<ConnId>;<Anrufer>;<Angerufene Nummer>;<Gerät>;"
    Andere Ereignistypen (CALL/CONNECT/DISCONNECT) sowie unparsebare Zeilen
    liefern None.
    """
    fields = line.strip().split(";")
    if len(fields) < 6 or fields[1] != "RING":
        return None
    return RingEvent(caller_number=fields[3], called_number=fields[4], device=fields[5])


class CallMonitorConnection:
    """Hält eine blockierende TCP-Verbindung zum CallMonitor-Port offen."""

    def __init__(self, address: str, port: int = CALL_MONITOR_PORT) -> None:
        self._address = address
        self._port = port
        self._socket: socket.socket | None = None

    def connect(self) -> None:
        self._socket = socket.create_connection(
            (self._address, self._port), timeout=_CONNECT_TIMEOUT_SECONDS
        )
        self._socket.settimeout(None)  # nach Verbindungsaufbau blockierend lesen

    def close(self) -> None:
        if self._socket is not None:
            # shutdown() statt nur close(): close() dekrementiert nur die
            # Referenzzählung des Python-Socket-Objekts (makefile() hält eine
            # eigene Referenz) und schließt den zugrunde liegenden OS-Deskriptor
            # dadurch nicht zuverlässig - ein blockierender recv() in einem
            # anderen Thread würde dann nicht unterbrochen. shutdown() wirkt
            # sofort auf OS-Ebene.
            try:
                self._socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self._socket.close()
            self._socket = None

    def ring_events(self) -> Iterator[RingEvent]:
        """Blockiert, bis Zeilen ankommen oder die Verbindung geschlossen wird."""
        if self._socket is None:
            raise RuntimeError("connect() muss vor ring_events() aufgerufen werden")
        with self._socket.makefile("r", encoding="utf-8") as stream:
            for line in stream:
                event = parse_ring_event(line)
                if event is not None:
                    yield event
