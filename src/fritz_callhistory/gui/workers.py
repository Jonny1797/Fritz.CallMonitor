"""QThread-Wrapper, damit blockierende Fritz!Box-/DB-Aufrufe die GUI nicht einfrieren."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QThread, Signal

from fritz_callhistory.fritz.exceptions import FritzBoxError

SyncFn = Callable[[], tuple[int, int]]
ImportFromBoxFn = Callable[[], int]
DialFn = Callable[[str], None]
VoicemailAudioFn = Callable[[], bytes]
ListPhonebooksFn = Callable[[], list[tuple[int, str]]]


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


class ImportFromBoxWorker(QThread):
    """Führt den einmaligen "Von Box importieren"-Zug (fritz/client.py's
    phonebook_contacts_detailed() -> LocalPhonebookRepository) in einem
    eigenen Thread aus - gleiche Form wie SyncWorker."""

    finished_import = Signal(int)  # Anzahl importierter/aktualisierter Kontakte
    import_failed = Signal(str)

    def __init__(self, import_fn: ImportFromBoxFn, parent=None) -> None:
        super().__init__(parent)
        self._import_fn = import_fn

    def run(self) -> None:
        try:
            imported = self._import_fn()
        except FritzBoxError as exc:
            self.import_failed.emit(str(exc))
            return
        except Exception as exc:  # Thread darf nie stillschweigend sterben
            self.import_failed.emit(f"Unerwarteter Fehler: {exc}")
            return
        self.finished_import.emit(imported)


class DialWorker(QThread):
    """Führt einen einzelnen Wählhilfe-Anruf (fritz/client.py's dial_number())
    in einem eigenen Thread aus - gleiche Form wie SyncWorker. *dial_fn* ist ein
    parameterloser Closure (die Nummer ist bereits eingebrannt), damit dieser
    Worker wie die anderen keine Kenntnis von Fritz!Box/Config braucht."""

    dial_succeeded = Signal()
    dial_failed = Signal(str)

    def __init__(self, dial_fn: Callable[[], None], parent=None) -> None:
        super().__init__(parent)
        self._dial_fn = dial_fn

    def run(self) -> None:
        try:
            self._dial_fn()
        except FritzBoxError as exc:
            self.dial_failed.emit(str(exc))
            return
        except Exception as exc:  # Thread darf nie stillschweigend sterben
            self.dial_failed.emit(f"Unerwarteter Fehler: {exc}")
            return
        self.dial_succeeded.emit()


class VoicemailActionWorker(QThread):
    """Führt eine einzelne Box-Aktion auf einer Anrufbeantworter-Nachricht aus
    (Gelesen-Markieren oder Löschen) in einem eigenen Thread - gleiche Form wie
    DialWorker, wiederverwendet für beide Aktionen (der jeweilige Closure trägt
    schon die Zielnachricht in sich)."""

    action_succeeded = Signal()
    action_failed = Signal(str)

    def __init__(self, action_fn: Callable[[], None], parent=None) -> None:
        super().__init__(parent)
        self._action_fn = action_fn

    def run(self) -> None:
        try:
            self._action_fn()
        except FritzBoxError as exc:
            self.action_failed.emit(str(exc))
            return
        except Exception as exc:  # Thread darf nie stillschweigend sterben
            self.action_failed.emit(f"Unerwarteter Fehler: {exc}")
            return
        self.action_succeeded.emit()


class PhonebookListWorker(QThread):
    """Holt die verfügbaren Telefonbücher (fritz/client.py's phonebooks()) in
    einem eigenen Thread - gleiche Form wie SyncWorker. Wird von MainWindow
    (nicht von SettingsDialog!) gehalten, siehe _open_settings_dialog()."""

    finished_listing = Signal(list)  # list[tuple[int, str]]
    listing_failed = Signal(str)

    def __init__(self, list_fn: ListPhonebooksFn, parent=None) -> None:
        super().__init__(parent)
        self._list_fn = list_fn

    def run(self) -> None:
        try:
            phonebooks = self._list_fn()
        except FritzBoxError as exc:
            self.listing_failed.emit(str(exc))
            return
        except Exception as exc:  # Thread darf nie stillschweigend sterben
            self.listing_failed.emit(f"Unerwarteter Fehler: {exc}")
            return
        self.finished_listing.emit(phonebooks)


class VoicemailAudioWorker(QThread):
    """Holt die Audiodaten einer einzelnen Anrufbeantworter-Nachricht
    (fritz/client.py's voicemail_audio()) in einem eigenen Thread - gleiche Form
    wie DialWorker. *audio_fn* ist ein parameterloser Closure (der Pfad ist bereits
    eingebrannt)."""

    audio_ready = Signal(bytes)
    audio_failed = Signal(str)

    def __init__(self, audio_fn: VoicemailAudioFn, parent=None) -> None:
        super().__init__(parent)
        self._audio_fn = audio_fn

    def run(self) -> None:
        try:
            data = self._audio_fn()
        except FritzBoxError as exc:
            self.audio_failed.emit(str(exc))
            return
        except Exception as exc:  # Thread darf nie stillschweigend sterben
            self.audio_failed.emit(f"Unerwarteter Fehler: {exc}")
            return
        self.audio_ready.emit(data)
