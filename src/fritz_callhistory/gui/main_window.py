"""Hauptfenster: Kontaktliste (Name/Nummer/letzter Kontakt/Anzahl Anrufe),
Suche, Detailansicht und Sync-Button (im Hintergrund-Thread)."""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from fritz_callhistory.db.repository import ContactRepository
from fritz_callhistory.gui.contact_detail import ContactDetailWidget
from fritz_callhistory.gui.models import ContactListModel
from fritz_callhistory.gui.workers import SyncFn, SyncWorker

_SEARCH_DEBOUNCE_MS = 250


class MainWindow(QMainWindow):
    def __init__(
        self,
        connection: sqlite3.Connection,
        sync_fn: SyncFn | None = None,
        auto_sync_interval_minutes: int | None = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("Fritz!Box Anrufhistorie")
        self.resize(900, 600)

        self._sync_fn = sync_fn
        self._sync_thread: SyncWorker | None = None

        self._contacts_repo = ContactRepository(connection)
        self._contact_model = ContactListModel()

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Suche nach Name oder Nummer …")
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(_SEARCH_DEBOUNCE_MS)
        self._search_timer.timeout.connect(self.reload_contacts)
        self._search_edit.textChanged.connect(lambda _: self._search_timer.start())

        self._sync_button = QPushButton("Jetzt synchronisieren")
        self._sync_button.clicked.connect(self._trigger_sync)
        self._sync_button.setEnabled(self._sync_fn is not None)

        self._table = QTableView()
        self._table.setModel(self._contact_model)
        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.selectionModel().selectionChanged.connect(self._on_selection_changed)

        self._detail = ContactDetailWidget(connection)
        self._contact_model.modelReset.connect(self._detail.clear)

        splitter = QSplitter()
        splitter.addWidget(self._table)
        splitter.addWidget(self._detail)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)

        top_row = QHBoxLayout()
        top_row.addWidget(self._search_edit)
        top_row.addWidget(self._sync_button)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addLayout(top_row)
        layout.addWidget(splitter)
        self.setCentralWidget(central)
        self.statusBar()

        if auto_sync_interval_minutes and self._sync_fn is not None:
            self._auto_sync_timer = QTimer(self)
            self._auto_sync_timer.setInterval(auto_sync_interval_minutes * 60 * 1000)
            self._auto_sync_timer.timeout.connect(self._trigger_sync)
            self._auto_sync_timer.start()

        self.reload_contacts()

    def reload_contacts(self) -> None:
        self._contact_model.set_contacts(self._contacts_repo.search(self._search_edit.text()))

    def _on_selection_changed(self, selected, deselected) -> None:
        indexes = selected.indexes()
        if not indexes:
            self._detail.clear()
            return
        contact = self._contact_model.contact_at(indexes[0].row())
        self._detail.show_contact(contact)

    def _trigger_sync(self) -> None:
        if self._sync_fn is None or (self._sync_thread is not None and self._sync_thread.isRunning()):
            return
        self._sync_button.setEnabled(False)
        self.statusBar().showMessage("Synchronisiere mit der Fritz!Box …")

        self._sync_thread = SyncWorker(self._sync_fn, parent=self)
        self._sync_thread.finished_sync.connect(self._on_sync_finished)
        self._sync_thread.sync_failed.connect(self._on_sync_failed)
        self._sync_thread.start()

    def _on_sync_finished(self, inserted: int, updated: int) -> None:
        self._sync_button.setEnabled(True)
        self.statusBar().showMessage(
            f"Sync abgeschlossen: {inserted} neue Anrufe, {updated} Kontakte aktualisiert", 5000
        )
        self.reload_contacts()

    def _on_sync_failed(self, message: str) -> None:
        self._sync_button.setEnabled(True)
        self.statusBar().showMessage(f"Sync fehlgeschlagen: {message}", 8000)
