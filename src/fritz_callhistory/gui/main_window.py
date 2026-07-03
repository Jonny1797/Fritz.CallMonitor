"""Hauptfenster: Kontaktliste (Name/Nummer/letzter Kontakt/Anzahl Anrufe),
Suche, Detailansicht und Sync-Button (im Hintergrund-Thread)."""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSplitter,
    QStyle,
    QSystemTrayIcon,
    QTabWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from fritz_callhistory.db.repository import ContactRepository
from fritz_callhistory.gui.all_calls_view import AllCallsView
from fritz_callhistory.gui.callmonitor_worker import CallMonitorThread
from fritz_callhistory.gui.contact_detail import ContactDetailWidget
from fritz_callhistory.gui.models import ContactListModel
from fritz_callhistory.gui.phonebook_view import PhonebookTab
from fritz_callhistory.gui.workers import ImportFromBoxFn, SyncFn, SyncWorker
from fritz_callhistory.sync.normalize import normalize_number

_SEARCH_DEBOUNCE_MS = 250
_CONTACT_NUMBER_COLUMN = 1


class MainWindow(QMainWindow):
    def __init__(
        self,
        connection: sqlite3.Connection,
        sync_fn: SyncFn | None = None,
        auto_sync_interval_minutes: int | None = None,
        fritzbox_address: str | None = None,
        import_from_box_fn: ImportFromBoxFn | None = None,
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
        self._table.doubleClicked.connect(self._on_contact_table_double_clicked)

        self._detail = ContactDetailWidget(connection)
        self._contact_model.modelReset.connect(self._detail.clear)

        splitter = QSplitter()
        splitter.addWidget(self._table)
        splitter.addWidget(self._detail)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)

        contacts_tab = QWidget()
        contacts_layout = QVBoxLayout(contacts_tab)
        contacts_layout.addWidget(self._search_edit)
        contacts_layout.addWidget(splitter)

        self._all_calls_view = AllCallsView(connection)
        self._all_calls_view.contact_selected.connect(self._on_all_calls_contact_selected)
        self._all_calls_view.new_missed_calls_changed.connect(self._on_new_missed_calls_changed)
        self._all_calls_view.live_call_ended.connect(self._trigger_sync)

        self._phonebook_tab = PhonebookTab(connection, import_from_box_fn=import_from_box_fn)
        self._phonebook_tab.contacts_changed.connect(self.reload_contacts)
        self._detail.number_double_clicked.connect(self._phonebook_tab.add_or_edit_number)
        self._all_calls_view.number_double_clicked.connect(self._phonebook_tab.add_or_edit_number)

        self._tabs = QTabWidget()
        self._tabs.addTab(contacts_tab, "Kontakte")
        self._tabs.addTab(self._all_calls_view, "Alle Anrufe")
        self._tabs.addTab(self._phonebook_tab, "Telefonbuch")
        # AllCallsView.__init__ hat _reload() bereits vor der obigen Signal-
        # Verbindung ausgefuehrt - die erste new_missed_calls_changed-Emission
        # kam daher ohne Empfaenger an. Deshalb hier einmalig den bereits
        # berechneten, gecachten Wert direkt abfragen statt nur aufs Signal zu vertrauen.
        self._update_all_calls_tab_label(self._all_calls_view.new_missed_calls_count)

        top_row = QHBoxLayout()
        top_row.addStretch()
        top_row.addWidget(self._sync_button)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addLayout(top_row)
        layout.addWidget(self._tabs)
        self.setCentralWidget(central)
        self.statusBar()

        if auto_sync_interval_minutes and self._sync_fn is not None:
            self._auto_sync_timer = QTimer(self)
            self._auto_sync_timer.setInterval(auto_sync_interval_minutes * 60 * 1000)
            self._auto_sync_timer.timeout.connect(self._trigger_sync)
            self._auto_sync_timer.start()

        self._tray_icon = QSystemTrayIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon), self
        )
        self._tray_icon.setToolTip("Fritz!Box Anrufhistorie")
        self._tray_icon.show()

        self._call_monitor: CallMonitorThread | None = None
        self._call_monitor_connection_lost_shown = False
        if fritzbox_address:
            self._call_monitor = CallMonitorThread(fritzbox_address, parent=self)
            self._call_monitor.ring.connect(self._on_ring)
            self._call_monitor.ring.connect(self._all_calls_view.on_live_ring)
            self._call_monitor.connected.connect(self._all_calls_view.on_live_connected)
            self._call_monitor.disconnected.connect(self._all_calls_view.on_live_disconnected)
            self._call_monitor.connection_lost.connect(self._on_call_monitor_connection_lost)
            self._call_monitor.connection_lost.connect(self._all_calls_view.clear_live_calls)
            self._call_monitor.start()

        self.reload_contacts()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._call_monitor is not None:
            self._call_monitor.stop()
            self._call_monitor.wait(2000)
        super().closeEvent(event)

    def _on_ring(self, connection_id: str, caller_number: str, called_number: str) -> None:
        normalized, is_anonymous = normalize_number(caller_number)
        if is_anonymous:
            message = "Unbekannte / unterdrückte Nummer"
        else:
            contact = self._contacts_repo.find_by_number(normalized)
            message = contact.display_name if (contact and contact.display_name) else normalized
        self._tray_icon.showMessage(
            "Eingehender Anruf", message, QSystemTrayIcon.MessageIcon.Information, 8000
        )

    def _update_all_calls_tab_label(self, count: int) -> None:
        label = f"Alle Anrufe ({count} neu verpasst)" if count else "Alle Anrufe"
        self._tabs.setTabText(1, label)

    def _on_new_missed_calls_changed(self, count: int) -> None:
        self._update_all_calls_tab_label(count)

    def _on_call_monitor_connection_lost(self, message: str) -> None:
        if self._call_monitor_connection_lost_shown:
            return
        self._call_monitor_connection_lost_shown = True
        self.statusBar().showMessage(
            "CallMonitor nicht erreichbar - ist der Wählcode #96*5* auf der Box aktiviert? "
            "(Verbindung wird automatisch weiter versucht.)",
            10000,
        )

    def reload_contacts(self) -> None:
        self._contact_model.set_contacts(self._contacts_repo.search(self._search_edit.text()))

    def _on_all_calls_contact_selected(self, contact_id: int) -> None:
        # search_timer.stop() ist noetig: search_edit.clear() loest ueber
        # textChanged sonst den 250ms-Debounce-Timer aus, der 250ms spaeter
        # einen zweiten, ueberfluessigen reload_contacts() feuern wuerde -
        # dessen modelReset raeumt ueber die bestehende Verbindung die gerade
        # frisch angezeigte Detailansicht wieder leer.
        self._search_edit.clear()
        self._search_timer.stop()
        self.reload_contacts()
        self._tabs.setCurrentIndex(0)
        row = self._contact_model.index_of(contact_id)
        if row is not None:
            self._table.selectRow(row)

    def _on_contact_table_double_clicked(self, index) -> None:
        if index.column() != _CONTACT_NUMBER_COLUMN:
            return
        contact = self._contact_model.contact_at(index.row())
        if contact.is_anonymous:
            return
        self._phonebook_tab.add_or_edit_number(contact.primary_number)

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
        self._all_calls_view.reload()

    def _on_sync_failed(self, message: str) -> None:
        self._sync_button.setEnabled(True)
        self.statusBar().showMessage(f"Sync fehlgeschlagen: {message}", 8000)
