"""QThread-Wrapper, damit blockierende Fritz!Box-/DB-Aufrufe die GUI nicht einfrieren."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QThread, Signal

from fritz_callhistory.fritz.exceptions import FritzBoxError

SyncFn = Callable[[], tuple[int, int]]


class SyncWorker(QThread):
    """Führt eine Sync-Funktion (Verbindung aufbauen + sync_calls + sync_phonebook)
    in einem eigenen Thread aus. Die *sync_fn* entscheidet, was genau synchronisiert
    wird - dieser Worker kennt weder Fritz!Box noch Config, nur das Ergebnis."""

    finished_sync = Signal(int, int)  # (neue Anrufe, aktualisierte Kontakte)
    sync_failed = Signal(str)

    def __init__(self, sync_fn: SyncFn, parent=None) -> None:
        super().__init__(parent)
        self._sync_fn = sync_fn

    def run(self) -> None:
        try:
            inserted, updated = self._sync_fn()
        except FritzBoxError as exc:
            self.sync_failed.emit(str(exc))
            return
        except Exception as exc:  # Thread darf nie stillschweigend sterben
            self.sync_failed.emit(f"Unerwarteter Fehler: {exc}")
            return
        self.finished_sync.emit(inserted, updated)
