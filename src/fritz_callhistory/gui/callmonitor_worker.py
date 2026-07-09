"""Dauerhaft laufender QThread, der auf Fritz!Box-CallMonitor-Ereignisse lauscht.

Reconnect-Schleife statt harter Fehlschlag: wenn #96*5* (noch) nicht aktiviert
ist oder die Box kurz nicht erreichbar ist, wird es in Intervallen erneut
versucht, ohne die GUI zu blockieren oder die App abstürzen zu lassen.
"""

from __future__ import annotations

import threading

from PySide6.QtCore import QThread, Signal

from fritz_callhistory.fritz.callmonitor import (
    CALL_MONITOR_PORT,
    CallMonitorConnection,
    ConnectEvent,
    DisconnectEvent,
    RingEvent,
)

_RECONNECT_DELAY_SECONDS = 10.0


class CallMonitorThread(QThread):
    ring = Signal(str, str, str)  # connection_id, caller_number, called_number
    connected = Signal(str)  # connection_id
    disconnected = Signal(str)  # connection_id
    connection_lost = Signal(str)

    def __init__(
        self,
        address: str,
        port: int = CALL_MONITOR_PORT,
        reconnect_delay_seconds: float = _RECONNECT_DELAY_SECONDS,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._address = address
        self._port = port
        self._reconnect_delay_seconds = reconnect_delay_seconds
        # Das eigentliche Abbruchsignal: ein Event statt eines Bool+Lock, weil
        # dessen wait() sowohl den Reconnect-Wartezeitraum (statt einem
        # unterbrechungsfreien time.sleep(), das stop() bis zu
        # reconnect_delay_seconds lang ignorieren würde) als auch die
        # Stop-Prüfung nach connect() sofort abbrechbar macht.
        self._stop_event = threading.Event()
        self._connection: CallMonitorConnection | None = None
        # Schützt nur den Zugriff auf self._connection zwischen stop() und run().
        self._connection_lock = threading.Lock()

    def stop(self) -> None:
        self._stop_event.set()
        with self._connection_lock:
            if self._connection is not None:
                self._connection.close()

    def run(self) -> None:
        while not self._stop_event.is_set():
            with self._connection_lock:
                self._connection = CallMonitorConnection(self._address, self._port)
            try:
                self._connection.connect()
            except OSError as exc:
                self.connection_lost.emit(str(exc))
            else:
                if self._stop_event.is_set():
                    self._connection.close()
                    return
                try:
                    for event in self._connection.events():
                        if isinstance(event, RingEvent):
                            self.ring.emit(
                                event.connection_id, event.caller_number, event.called_number
                            )
                        elif isinstance(event, ConnectEvent):
                            self.connected.emit(event.connection_id)
                        elif isinstance(event, DisconnectEvent):
                            self.disconnected.emit(event.connection_id)
                except OSError as exc:
                    self.connection_lost.emit(str(exc))

            if self._stop_event.is_set():
                return
            self._stop_event.wait(self._reconnect_delay_seconds)
