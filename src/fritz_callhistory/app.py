"""Einstiegspunkt: QApplication starten und MainWindow anzeigen."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QDialog

from fritz_callhistory import config as config_module
from fritz_callhistory import credentials
from fritz_callhistory.db.connection import connect
from fritz_callhistory.db.repository import CallRepository, ContactRepository, PhonebookRepository
from fritz_callhistory.fritz.client import FritzBoxClient
from fritz_callhistory.gui.credentials_dialog import CredentialsDialog
from fritz_callhistory.gui.main_window import MainWindow
from fritz_callhistory.gui.workers import SyncFn
from fritz_callhistory.paths import database_file
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
            )
            inserted = service.sync_calls()
            updated = service.sync_phonebook(cfg.resolved_phonebook_ids())
            return inserted, updated
        finally:
            worker_connection.close()

    return sync_fn


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
    )
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
