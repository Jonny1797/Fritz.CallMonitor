"""Einstiegspunkt: QApplication starten und MainWindow anzeigen."""

from __future__ import annotations

import os
import signal
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog

from fritz_callhistory import config as config_module
from fritz_callhistory import credentials
from fritz_callhistory.db.connection import connect
from fritz_callhistory.db.repository import (
    CallRepository,
    ContactRepository,
    LocalPhonebookRepository,
    PhonebookRepository,
    VoicemailMessageRecord,
    VoicemailRepository,
)
from fritz_callhistory.fritz.client import FritzBoxClient
from fritz_callhistory.gui.credentials_dialog import CredentialsDialog
from fritz_callhistory.gui.main_window import MainWindow
from fritz_callhistory.gui.voicemail_view import AudioFetchFn, VoicemailActionFn
from fritz_callhistory.gui.workers import DialFn, ImportFromBoxFn, SyncFn
from fritz_callhistory.paths import database_file
from fritz_callhistory.sync.normalize import normalize_number
from fritz_callhistory.sync.service import SyncService


def _build_sync_fn(cfg: config_module.Config) -> SyncFn | None:
    """Baut die Sync-Funktion für den SyncWorker-Thread.

    Der FritzBoxClient wird erst innerhalb der zurückgegebenen Funktion erzeugt
    (also erst im Hintergrund-Thread), damit der Verbindungsaufbau die GUI nicht
    blockiert. Aus demselben Grund öffnet sync_fn seine eigene SQLite-Connection,
    statt die des GUI-Threads mitzubenutzen: sqlite3-Connections dürfen nicht
    threadübergreifend verwendet werden (sonst sqlite3.ProgrammingError).
    """
    password = credentials.get_password(cfg.username) if cfg.username else None
    if not cfg.username or not password:
        return None

    def sync_fn() -> tuple[int, int]:
        worker_connection = connect(database_file())
        try:
            client = FritzBoxClient(cfg.address, cfg.username, password)
            service = SyncService(
                client,
                ContactRepository(worker_connection),
                CallRepository(worker_connection),
                PhonebookRepository(worker_connection),
                LocalPhonebookRepository(worker_connection),
                VoicemailRepository(worker_connection),
            )
            inserted = service.sync_calls()
            updated = service.sync_phonebook(cfg.resolved_phonebook_ids())
            service.sync_voicemail()
            return inserted, updated
        finally:
            worker_connection.close()

    return sync_fn


def _build_import_from_box_fn(cfg: config_module.Config) -> ImportFromBoxFn | None:
    """Baut die Funktion für den einmaligen "Von Box importieren"-Zug
    (ImportFromBoxWorker) - gleiches Verbindungsaufbau-/Threading-Muster wie
    _build_sync_fn (siehe dort für die Begründung).
    """
    password = credentials.get_password(cfg.username) if cfg.username else None
    if not cfg.username or not password:
        return None

    def import_from_box_fn() -> int:
        worker_connection = connect(database_file())
        try:
            client = FritzBoxClient(cfg.address, cfg.username, password)
            local_repo = LocalPhonebookRepository(worker_connection)
            ids = cfg.resolved_phonebook_ids() or client.phonebook_ids()
            imported = 0
            for phonebook_id in ids:
                for box_contact in client.phonebook_contacts_detailed(phonebook_id):
                    if not box_contact.name:
                        continue
                    numbers: list[tuple[str, str, str]] = []
                    for number in box_contact.numbers:
                        normalized, is_anonymous = normalize_number(number.value)
                        if not is_anonymous:
                            numbers.append((number.value, normalized, number.type))

                    existing = (
                        local_repo.find_by_box_uniqueid(box_contact.uniqueid)
                        if box_contact.uniqueid
                        else None
                    )
                    if existing:
                        # Die Box kennt kein "Standardnummer"-Konzept - eine
                        # zuvor lokal gesetzte Standardnummer muss über den
                        # vollen delete+reinsert von update() hinweg erhalten
                        # bleiben, gematcht über number_normalized (Zeilen-IDs
                        # überleben update() nicht, siehe db/repository.py).
                        existing_defaults = {
                            n.number_normalized for n in existing.numbers if n.is_default
                        }
                        numbers_with_default = [
                            (raw, normalized, number_type, normalized in existing_defaults)
                            for raw, normalized, number_type in numbers
                        ]
                        local_repo.update(
                            existing.id,
                            display_name=box_contact.name,
                            notes=existing.notes,
                            numbers=numbers_with_default,
                        )
                    else:
                        # "Adoptieren": ein zuvor rein lokal angelegter Kontakt mit
                        # exakt derselben Nummernmenge wird mit dieser Box-Id
                        # verknüpft statt dupliziert (siehe db/repository.py's
                        # find_local_only_contact_by_exact_numbers).
                        adopt_id = local_repo.find_local_only_contact_by_exact_numbers(
                            [n[1] for n in numbers]
                        )
                        if adopt_id is not None and box_contact.uniqueid:
                            local_repo.set_box_uniqueid(adopt_id, box_contact.uniqueid)
                        else:
                            local_repo.create(
                                display_name=box_contact.name,
                                notes=None,
                                numbers=[
                                    (raw, normalized, number_type, False)
                                    for raw, normalized, number_type in numbers
                                ],
                                box_uniqueid=box_contact.uniqueid,
                            )
                    imported += 1
            return imported
        finally:
            worker_connection.close()

    return import_from_box_fn


def _build_dial_fn(cfg: config_module.Config) -> DialFn | None:
    """Baut die Funktion für den einmaligen Anruf-Auslöse-Klick (DialWorker) -
    gleiches Verbindungsaufbau-Muster wie _build_sync_fn (siehe dort für die
    Begründung), aber ohne eigene DB-Verbindung, da dial_number() keine
    Datenbank berührt."""
    password = credentials.get_password(cfg.username) if cfg.username else None
    if not cfg.username or not password:
        return None

    def dial_fn(number: str) -> None:
        client = FritzBoxClient(cfg.address, cfg.username, password)
        client.dial_number(number)

    return dial_fn


def _resolve_box_index(client: FritzBoxClient, message: VoicemailMessageRecord) -> int | None:
    """box_index ist nicht stabil über Löschungen hinweg (siehe fritz/client.py's
    VoicemailMessage.box_index-Kommentar) und wird deshalb nicht in der DB
    gespeichert - jeder Aufruf, der ihn braucht (Gelesen-Markieren, Löschen), muss
    ihn unmittelbar vorher per Live-Abgleich über (box_path, message_date) neu
    ermitteln, statt einen zwischengespeicherten Wert zu benutzen."""
    for candidate in client.voicemail_messages(message.tam_index):
        if candidate.path == message.box_path and candidate.date == message.message_date:
            return candidate.box_index
    return None


def _build_voicemail_audio_fn(cfg: config_module.Config) -> AudioFetchFn | None:
    """Baut die Funktion für den einmaligen Abspiel-Klick (VoicemailAudioWorker) -
    gleiches Verbindungsaufbau-Muster wie _build_dial_fn. Markiert die Nachricht
    zusätzlich auf der Box selbst als gelesen (X_AVM-DE_TAM/MarkMessage, verifiziert
    gegen eine echte Box); VoicemailView flippt den lokalen is_new-Zustand direkt im
    Anschluss selbst (VoicemailRepository.mark_read_locally), damit die rot/fett-
    Markierung nicht erst auf den nächsten Sync warten muss."""
    password = credentials.get_password(cfg.username) if cfg.username else None
    if not cfg.username or not password:
        return None

    def voicemail_audio_fn(message: VoicemailMessageRecord) -> bytes:
        client = FritzBoxClient(cfg.address, cfg.username, password)
        audio = client.voicemail_audio(message.box_path)
        box_index = _resolve_box_index(client, message)
        if box_index is not None:
            client.voicemail_mark_read(message.tam_index, box_index)
        return audio

    return voicemail_audio_fn


def _build_voicemail_mark_read_fn(cfg: config_module.Config) -> VoicemailActionFn | None:
    """Baut die Funktion für den expliziten "Gelesen"-Button (VoicemailActionWorker) -
    gleiches Verbindungsaufbau-/Index-Auflösungs-Muster wie _build_voicemail_audio_fn,
    aber ohne den Audio-Download: erlaubt, eine Nachricht als gelesen zu markieren,
    ohne sie abzuspielen."""
    password = credentials.get_password(cfg.username) if cfg.username else None
    if not cfg.username or not password:
        return None

    def voicemail_mark_read_fn(message: VoicemailMessageRecord) -> None:
        client = FritzBoxClient(cfg.address, cfg.username, password)
        box_index = _resolve_box_index(client, message)
        if box_index is not None:
            client.voicemail_mark_read(message.tam_index, box_index)

    return voicemail_mark_read_fn


def _build_voicemail_delete_fn(cfg: config_module.Config) -> VoicemailActionFn | None:
    """Baut die Funktion für den "Löschen"-Button (VoicemailActionWorker) - löscht
    die Nachricht echt auf der Box (X_AVM-DE_TAM/DeleteMessage). Die lokale Zeile wird
    nicht hier, sondern von VoicemailView nach erfolgreichem Abschluss entfernt
    (VoicemailRepository.delete), damit ein fehlgeschlagener Box-Aufruf die lokale
    Kopie nicht verwaist zurück lässt."""
    password = credentials.get_password(cfg.username) if cfg.username else None
    if not cfg.username or not password:
        return None

    def voicemail_delete_fn(message: VoicemailMessageRecord) -> None:
        client = FritzBoxClient(cfg.address, cfg.username, password)
        box_index = _resolve_box_index(client, message)
        if box_index is not None:
            client.voicemail_delete(message.tam_index, box_index)

    return voicemail_delete_fn


def _handle_sigint(*_args) -> None:
    """Strg+C beendet den Prozess sofort und hart, statt über window.close()
    zu gehen: MainWindow.closeEvent() wartet bei einem normalen Schliessen
    bewusst auf noch laufende Worker-Threads (Sync-/ImportFromBoxWorker) - das
    ist für einen Klick auf X das richtige Verhalten, aber für Strg+C
    erwartet man in einem Terminal-Programm einen sofortigen Abbruch, egal was
    gerade läuft (z.B. ein Netzwerkaufruf, der trotz Timeout in
    fritz/client.py hängt, etwa durch einen blockierenden DNS-Lookup, den
    requests' timeout-Parameter nicht abdeckt). os._exit() umgeht Qt's/Pythons
    normale Aufräum-Reihenfolge komplett - kein qFatal-Crash-Risiko durch noch
    laufende QThreads, da deren Destruktoren gar nicht erst aufgerufen werden;
    das Betriebssystem räumt Sockets/Dateien beim Prozessende ohnehin auf, und
    jeder DB-Schreibzugriff committet bereits einzeln (siehe db/repository.py),
    es geht also höchstens ein einzelner, gerade laufender Schreibzugriff
    verloren."""
    os._exit(130)  # 128 + SIGINT, übliche Exitcode-Konvention


def main() -> int:
    app = QApplication(sys.argv)
    connection = connect(database_file())
    cfg = config_module.load()

    if not cfg.username or not credentials.get_password(cfg.username):
        dialog = CredentialsDialog(cfg)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            cfg = dialog.save(cfg)

    window = MainWindow(
        connection,
        sync_fn=_build_sync_fn(cfg),
        auto_sync_interval_minutes=cfg.sync_interval_minutes,
        fritzbox_address=cfg.address,
        import_from_box_fn=_build_import_from_box_fn(cfg),
        show_incoming_call_popup=cfg.show_incoming_call_popup,
        dial_fn=_build_dial_fn(cfg),
        voicemail_audio_fn=_build_voicemail_audio_fn(cfg),
        voicemail_mark_read_fn=_build_voicemail_mark_read_fn(cfg),
        voicemail_delete_fn=_build_voicemail_delete_fn(cfg),
    )
    window.show()

    # Qt's C++-Eventloop liefert SIGINT erst, wenn wieder Python-Bytecode
    # läuft; der No-Op-Timer sorgt dafür, dass das zeitnah passiert statt
    # erst bei der nächsten GUI-Interaktion (siehe _handle_sigint()).
    signal.signal(signal.SIGINT, _handle_sigint)
    signal_timer = QTimer()
    signal_timer.timeout.connect(lambda: None)
    signal_timer.start(200)

    exit_code = app.exec()
    # os._exit() statt return: sobald app.exec() zurückkehrt (regulär über
    # MainWindow.closeEvent()'s expliziten QApplication.quit()-Aufruf, oder
    # über quitOnLastWindowClosed), soll der Prozess sofort enden - nicht
    # über Pythons normale Interpreter-Shutdown-Sequenz, in der PySide beim
    # atexit-Handling alle verbliebenen QObjects zerstört (inkl. etwaiger
    # noch lebender QThreads, was den ursprünglichen "QThread: Destroyed
    # while thread ... is still running"-SIGABRT auslöst). Jeder
    # DB-Schreibzugriff committet bereits einzeln (siehe db/repository.py),
    # ein abgebrochener Shutdown verliert also höchstens einen einzelnen,
    # gerade laufenden Schreibzugriff.
    os._exit(exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
