"""Client für den Fritz!Box CallMonitor (Port 1012).

Separates Feature, unabhängig von TR-064/fritzconnection: ein einfaches
Text-Protokoll über eine rohe TCP-Verbindung, das Ereignisse wie RING/CALL/
CONNECT/DISCONNECT streamt. Muss auf der Box einmalig per Wählcode #96*5* von
einem angeschlossenen Telefon aus aktiviert werden - ohne das schlägt der
Verbindungsaufbau fehl (Connection refused), auch wenn TR-064 einwandfrei
funktioniert.
"""

from __future__ import annotations

import select
import socket
from collections.abc import Iterator
from dataclasses import dataclass

CALL_MONITOR_PORT = 1012
_CONNECT_TIMEOUT_SECONDS = 5.0
_RECV_BUFFER_SIZE = 4096


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
        # Self-Pipe-Trick: ein blockierendes recv() in events() soll aus einem
        # anderen Thread heraus abbrechbar sein. shutdown() auf den Socket
        # weckt einen blockierten recv() zwar ueblicherweise auf, aber das
        # haengt vom OS-Timing ab (das brachte bereits SIGABRTs beim App-Beenden,
        # wenn der QThread nicht rechtzeitig aufwachte). select() ueber Socket
        # UND diese Wakeup-Pipe gemeinsam macht den Abbruch stattdessen
        # deterministisch: close() schreibt ein Byte, select() kehrt sofort
        # zurueck, ganz unabhaengig vom shutdown()-Wakeup.
        self._wakeup_r, self._wakeup_w = socket.socketpair()

    def connect(self) -> None:
        self._socket = socket.create_connection(
            (self._address, self._port), timeout=_CONNECT_TIMEOUT_SECONDS
        )
        self._socket.settimeout(None)  # nach Verbindungsaufbau blockierend lesen

    def close(self) -> None:
        try:
            self._wakeup_w.send(b"x")
        except OSError:
            pass
        self._wakeup_w.close()
        if self._socket is not None:
            try:
                self._socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self._socket.close()
            self._socket = None

    def events(self) -> Iterator[CallMonitorEvent]:
        """Blockiert, bis Zeilen ankommen oder die Verbindung geschlossen wird."""
        sock = self._socket
        if sock is None:
            raise RuntimeError("connect() muss vor events() aufgerufen werden")
        buffer = b""
        try:
            while True:
                readable, _, _ = select.select([sock, self._wakeup_r], [], [])
                if self._wakeup_r in readable:
                    return
                chunk = sock.recv(_RECV_BUFFER_SIZE)
                if not chunk:
                    return
                buffer += chunk
                while b"\n" in buffer:
                    raw_line, buffer = buffer.split(b"\n", 1)
                    event = parse_event(raw_line.decode("utf-8", errors="replace"))
                    if event is not None:
                        yield event
        finally:
            self._wakeup_r.close()
