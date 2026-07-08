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
)
from fritz_callhistory.fritz.client import FritzBoxClient
from fritz_callhistory.gui.credentials_dialog import CredentialsDialog
from fritz_callhistory.gui.main_window import MainWindow
from fritz_callhistory.gui.workers import ImportFromBoxFn, SyncFn
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
            )
            inserted = service.sync_calls()
            updated = service.sync_phonebook(cfg.resolved_phonebook_ids())
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
                        local_repo.update(
                            existing.id,
                            display_name=box_contact.name,
                            notes=existing.notes,
                            numbers=numbers,
                        )
                    else:
                        # "Adoptieren": ein zuvor rein lokal angelegter Kontakt mit
                        # exakt derselben Nummernmenge wird mit dieser Box-Id
                        # verknuepft statt dupliziert (siehe db/repository.py's
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
                                numbers=numbers,
                                box_uniqueid=box_contact.uniqueid,
                            )
                    imported += 1
            return imported
        finally:
            worker_connection.close()

    return import_from_box_fn


def _handle_sigint(*_args) -> None:
    """Strg+C beendet den Prozess sofort und hart, statt ueber window.close()
    zu gehen: MainWindow.closeEvent() wartet bei einem normalen Schliessen
    bewusst auf noch laufende Worker-Threads (Sync-/ImportFromBoxWorker) - das
    ist fuer einen Klick auf X das richtige Verhalten, aber fuer Strg+C
    erwartet man in einem Terminal-Programm einen sofortigen Abbruch, egal was
    gerade laeuft (z.B. ein Netzwerkaufruf, der trotz Timeout in
    fritz/client.py haengt, etwa durch einen blockierenden DNS-Lookup, den
    requests' timeout-Parameter nicht abdeckt). os._exit() umgeht Qt's/Pythons
    normale Aufraeum-Reihenfolge komplett - kein qFatal-Crash-Risiko durch noch
    laufende QThreads, da deren Destruktoren gar nicht erst aufgerufen werden;
    das Betriebssystem raeumt Sockets/Dateien beim Prozessende ohnehin auf, und
    jeder DB-Schreibzugriff committet bereits einzeln (siehe db/repository.py),
    es geht also hoechstens ein einzelner, gerade laufender Schreibzugriff
    verloren."""
    os._exit(130)  # 128 + SIGINT, uebliche Exitcode-Konvention


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
    )
    window.show()

    # Qt's C++-Eventloop liefert SIGINT erst, wenn wieder Python-Bytecode
    # laeuft; der No-Op-Timer sorgt dafuer, dass das zeitnah passiert statt
    # erst bei der naechsten GUI-Interaktion (siehe _handle_sigint()).
    signal.signal(signal.SIGINT, _handle_sigint)
    signal_timer = QTimer()
    signal_timer.timeout.connect(lambda: None)
    signal_timer.start(200)

    exit_code = app.exec()
    # os._exit() statt return: sobald app.exec() zurueckkehrt (regulaer ueber
    # MainWindow.closeEvent()'s expliziten QApplication.quit()-Aufruf, oder
    # ueber quitOnLastWindowClosed), soll der Prozess sofort enden - nicht
    # ueber Pythons normale Interpreter-Shutdown-Sequenz, in der PySide beim
    # atexit-Handling alle verbliebenen QObjects zerstoert (inkl. etwaiger
    # noch lebender QThreads, was den urspruenglichen "QThread: Destroyed
    # while thread ... is still running"-SIGABRT ausloest). Jeder
    # DB-Schreibzugriff committet bereits einzeln (siehe db/repository.py),
    # ein abgebrochener Shutdown verliert also hoechstens einen einzelnen,
    # gerade laufenden Schreibzugriff.
    os._exit(exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
