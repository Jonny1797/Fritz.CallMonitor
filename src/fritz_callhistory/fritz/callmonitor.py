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
    connection_id: str
    caller_number: str
    called_number: str
    device: str


@dataclass
class ConnectEvent:
    connection_id: str


@dataclass
class DisconnectEvent:
    connection_id: str


CallMonitorEvent = RingEvent | ConnectEvent | DisconnectEvent


def parse_event(line: str) -> CallMonitorEvent | None:
    """Parst eine CallMonitor-Zeile.

    Zeilenformate (offizielle AVM-Beispiele):
        "<Datum>;RING;<ConnId>;<Anrufer>;<Angerufene Nummer>;<Gerät>;"
        "<Datum>;CONNECT;<ConnId>;<Nebenstelle>;<Nummer>;"
        "<Datum>;DISCONNECT;<ConnId>;<Nebenstelle>;"

    Bei CONNECT/DISCONNECT wird bewusst nur die ConnId ausgewertet: das dritte
    Feld dort ist die interne Nebenstelle, keine Anrufdauer (ein offizielles
    AVM-Beispiel zeigt "CONNECT;2;4;..." gefolgt von "DISCONNECT;2;4;" - die "4"
    bleibt zwischen beiden Zeilen gleich, obwohl der Anruf mehrere Sekunden
    dauerte). Die tatsächliche Dauer liefert ohnehin erst der spaetere Sync
    von der Box, nicht das CallMonitor-Protokoll.

    CALL-Ereignisse (ausgehende Anrufe) sowie unparsebare Zeilen liefern None.
    """
    fields = line.strip().split(";")
    if len(fields) < 3:
        return None
    kind = fields[1]
    connection_id = fields[2]
    if kind == "RING":
        if len(fields) < 6:
            return None
        return RingEvent(
            connection_id=connection_id,
            caller_number=fields[3],
            called_number=fields[4],
            device=fields[5],
        )
    if kind == "CONNECT":
        return ConnectEvent(connection_id=connection_id)
    if kind == "DISCONNECT":
        return DisconnectEvent(connection_id=connection_id)
    return None


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

    def events(self) -> Iterator[CallMonitorEvent]:
        """Blockiert, bis Zeilen ankommen oder die Verbindung geschlossen wird."""
        if self._socket is None:
            raise RuntimeError("connect() muss vor events() aufgerufen werden")
        with self._socket.makefile("r", encoding="utf-8") as stream:
            for line in stream:
                event = parse_event(line)
                if event is not None:
                    yield event
