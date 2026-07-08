"""Hauptfenster: Kontaktliste (Name/Nummer/letzter Kontakt/Anzahl Anrufe),
Suche, Detailansicht und Sync-Button (im Hintergrund-Thread)."""

from __future__ import annotations

import os
import sqlite3

from PySide6.QtCore import QThread, QTimer, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
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

from fritz_callhistory.db.repository import ContactRepository, LocalPhonebookRepository
from fritz_callhistory.gui.all_calls_view import AllCallsView
from fritz_callhistory.gui.callmonitor_worker import CallMonitorThread
from fritz_callhistory.gui.contact_detail import ContactDetailWidget
from fritz_callhistory.gui.incoming_call_popup import IncomingCallPopup
from fritz_callhistory.gui.models import (
    ContactListModel,
    DataclassSortProxy,
    install_call_context_menu,
    install_tristate_sorting,
)
from fritz_callhistory.gui.phonebook_view import PhonebookTab
from fritz_callhistory.gui.workers import DialFn, DialWorker, ImportFromBoxFn, SyncFn, SyncWorker
from fritz_callhistory.sync.normalize import normalize_number

_SEARCH_DEBOUNCE_MS = 250
_CONTACT_PHONEBOOK_COLUMNS = (0, 1)  # Name, Nummer
# Letzte Absicherung fuer closeEvent(): SyncWorker/ImportFromBoxWorker haben
# in fritz/client.py zwar ein Netzwerk-Timeout, das deckt aber z.B. keinen
# haengenden DNS-Lookup ab (socket.getaddrinfo() kennt kein Timeout). Damit
# das Beenden trotzdem nie unbegrenzt haengen bleibt, wird nach dieser Frist
# hart abgebrochen, falls dann immer noch ein Worker-Thread laeuft.
_SHUTDOWN_FAILSAFE_MS = 30_000


class MainWindow(QMainWindow):
    def __init__(
        self,
        connection: sqlite3.Connection,
        sync_fn: SyncFn | None = None,
        auto_sync_interval_minutes: int | None = None,
        fritzbox_address: str | None = None,
        import_from_box_fn: ImportFromBoxFn | None = None,
        show_incoming_call_popup: bool = True,
        dial_fn: DialFn | None = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("Fritz!Box Anrufhistorie")
        self.resize(900, 600)

        self._sync_fn = sync_fn
        self._sync_thread: SyncWorker | None = None
        self._dial_fn = dial_fn
        self._dial_thread: DialWorker | None = None
        self._close_requested = False
        self._shutdown_failsafe_timer: QTimer | None = None

        self._contacts_repo = ContactRepository(connection)
        self._local_phonebook_repo = LocalPhonebookRepository(connection)
        self._contact_model = ContactListModel()
        self._show_incoming_call_popup = show_incoming_call_popup
        self._incoming_call_popups: dict[str, IncomingCallPopup] = {}

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

        self._contact_proxy = DataclassSortProxy(
            row_getter=self._contact_model.contact_at,
            key_fns={
                0: lambda c: (c.display_name or "").lower(),
                1: lambda c: c.primary_number,
                2: lambda c: c.last_call_date,
                3: lambda c: c.call_count,
            },
        )
        self._contact_proxy.setSourceModel(self._contact_model)

        self._table = QTableView()
        self._table.setModel(self._contact_proxy)
        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.selectionModel().selectionChanged.connect(self._on_selection_changed)
        self._table.doubleClicked.connect(self._on_contact_table_double_clicked)
        install_tristate_sorting(self._table, self._contact_proxy)
        install_call_context_menu(
            self._table, self._contact_proxy, self._contact_number_for_row, self._dial_number
        )

        self._detail = ContactDetailWidget(connection)
        self._contact_model.modelReset.connect(self._detail.clear)
        self._detail.call_requested.connect(self._dial_number)

        # Titel/Untertitel des ausgewaehlten Kontakts laufen ueber die gesamte
        # Breite OBERHALB des Splitters, statt (wie frueher) nur ueber der
        # rechten Anrufliste zu stehen - sonst waere die linke Kontaktliste um
        # genau diese Kopfzeilenhoehe kuerzer als die rechte Tabelle (der
        # Splitter gibt beiden Kindern dieselbe Gesamthoehe, aber nur die
        # rechte Seite haette intern eine Kopfzeile). So haben beide Splitter-
        # Kinder von Anfang an nur eine Tabelle als Inhalt und werden dadurch
        # automatisch gleich hoch.
        detail_header_row = QHBoxLayout()
        detail_header_row.addWidget(self._detail.title_label)
        detail_header_row.addWidget(self._detail.subtitle_label)
        detail_header_row.addStretch()

        splitter = QSplitter()
        splitter.addWidget(self._table)
        splitter.addWidget(self._detail)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)

        contacts_tab = QWidget()
        contacts_layout = QVBoxLayout(contacts_tab)
        contacts_layout.addWidget(self._search_edit)
        contacts_layout.addLayout(detail_header_row)
        # stretch=1: ohne das teilt Qt den uebrigen vertikalen Platz zwischen
        # der Kopfzeile (QLabels sind per Default "Preferred", also wachstums-
        # faehig, nicht nur der Splitter) etwa haelftig auf - der Splitter soll
        # aber den gesamten Platz bekommen, die Kopfzeile nur ihre Zeilenhoehe.
        contacts_layout.addWidget(splitter, 1)

        self._all_calls_view = AllCallsView(connection)
        self._all_calls_view.contact_selected.connect(self._on_all_calls_contact_selected)
        self._all_calls_view.new_missed_calls_changed.connect(self._on_new_missed_calls_changed)
        self._all_calls_view.live_call_ended.connect(self._trigger_sync)
        self._all_calls_view.call_requested.connect(self._dial_number)

        self._phonebook_tab = PhonebookTab(connection, import_from_box_fn=import_from_box_fn)
        self._phonebook_tab.contacts_changed.connect(self.reload_contacts)
        self._phonebook_tab.call_requested.connect(self._dial_number)
        self._detail.number_double_clicked.connect(self._phonebook_tab.add_or_edit_number)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._all_calls_view, "Alle Anrufe")
        self._tabs.addTab(contacts_tab, "Kontakte")
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

        # Verzoegert per singleShot(0, ...) statt direktem Aufruf: so kehrt
        # __init__ zuerst zurueck und das Fenster wird sichtbar, bevor der
        # Sync-Thread im Hintergrund lostippt.
        QTimer.singleShot(0, self._trigger_sync)

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
            self._call_monitor.connected.connect(self._close_incoming_call_popup)
            self._call_monitor.disconnected.connect(self._close_incoming_call_popup)
            self._call_monitor.connection_lost.connect(self._on_call_monitor_connection_lost)
            self._call_monitor.connection_lost.connect(self._all_calls_view.clear_live_calls)
            self._call_monitor.start()

        self.reload_contacts()

    def _busy_worker_threads(self) -> list[QThread]:
        """SyncWorker/ImportFromBoxWorker/DialWorker fuehren einen einzelnen
        blockierenden Netzwerkaufruf ohne Abbruchpunkte aus - alle drei muessen
        hier erkannt werden, damit closeEvent() das Fenster nicht schliesst,
        waehrend einer von ihnen noch laeuft (siehe closeEvent() fuer die
        Begruendung)."""
        threads: list[QThread] = []
        if self._sync_thread is not None and self._sync_thread.isRunning():
            threads.append(self._sync_thread)
        import_thread = self._phonebook_tab.import_thread
        if import_thread is not None and import_thread.isRunning():
            threads.append(import_thread)
        if self._dial_thread is not None and self._dial_thread.isRunning():
            threads.append(self._dial_thread)
        return threads

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._close_requested:
            self._close_requested = True
            if self._call_monitor is not None:
                self._call_monitor.stop()

        # Ein festes wait(N) koennte ablaufen, waehrend so ein Thread noch in
        # seinem HTTP-Request steckt, und Qt wuerde ihn beim Zerstoeren des
        # Fensters mit SIGABRT abbrechen. Stattdessen wird das Fenster nur
        # versteckt (wirkt fuer den Nutzer bereits geschlossen); sobald der
        # letzte betroffene Thread von selbst fertig ist, loest sein
        # finished-Signal close() erneut aus - dann ist die Liste leer und der
        # eigentliche Schliessvorgang laeuft durch.
        busy_threads = self._busy_worker_threads()
        if busy_threads:
            self.hide()
            event.ignore()
            for thread in busy_threads:
                thread.finished.connect(self.close, Qt.ConnectionType.UniqueConnection)
            if self._shutdown_failsafe_timer is None:
                self._shutdown_failsafe_timer = QTimer(self)
                self._shutdown_failsafe_timer.setSingleShot(True)
                self._shutdown_failsafe_timer.timeout.connect(self._force_exit_if_still_busy)
                self._shutdown_failsafe_timer.start(_SHUTDOWN_FAILSAFE_MS)
            return

        if self._call_monitor is not None:
            self._call_monitor.wait(2000)
        super().closeEvent(event)

        # quitOnLastWindowClosed (Qt's impliziter "letztes Fenster zu ->
        # beenden"-Mechanismus) hat sich in der Praxis als nicht zuverlaessig
        # herausgestellt, um app.exec() tatsaechlich zurueckkehren zu lassen -
        # vermutlich abhaengig von Plattform/Compositor und dem hier immer
        # sichtbaren QSystemTrayIcon. Explizit quit() aufzurufen macht das
        # unabhaengig davon; main() in app.py sorgt zusaetzlich dafuer, dass
        # der Prozess unmittelbar endet, sobald app.exec() zurueckkehrt (statt
        # sich auf Pythons normale, langsamere Aufraeum-Reihenfolge zu
        # verlassen).
        app_instance = QApplication.instance()
        if app_instance is not None:
            app_instance.quit()

    def _force_exit_if_still_busy(self) -> None:
        # Feuert nur, wenn ein Worker-Thread _SHUTDOWN_FAILSAFE_MS nach dem
        # ersten Schliessversuch immer noch laeuft - regulaer erfolgreiche
        # Sync-/Import-Vorgaenge haben laengst ueber ihr finished-Signal einen
        # erneuten, diesmal erfolgreichen close() ausgeloest und diese Methode
        # laeuft dann entweder gar nicht mehr oder trifft auf eine leere Liste.
        if self._busy_worker_threads():
            os._exit(1)

    def _on_ring(self, connection_id: str, caller_number: str, called_number: str) -> None:
        normalized, is_anonymous = normalize_number(caller_number)
        contact_id = None
        notes = None
        if is_anonymous:
            message = "Unbekannte / unterdrückte Nummer"
        else:
            contact = self._contacts_repo.find_by_number(normalized)
            message = contact.display_name if (contact and contact.display_name) else normalized
            contact_id = contact.id if contact else None
            local_contact = self._local_phonebook_repo.find_by_number(normalized)
            notes = local_contact.notes if local_contact else None
        self._tray_icon.showMessage(
            "Eingehender Anruf", message, QSystemTrayIcon.MessageIcon.Information, 8000
        )
        if self._show_incoming_call_popup:
            self._show_incoming_call_window(
                connection_id, message, "" if is_anonymous else normalized, notes, contact_id
            )

    def _show_incoming_call_window(
        self,
        connection_id: str,
        title: str,
        subtitle: str,
        notes: str | None,
        contact_id: int | None,
    ) -> None:
        popup = IncomingCallPopup(connection_id, title, subtitle, notes, contact_id, parent=None)
        popup.open_contact_requested.connect(self._on_all_calls_contact_selected)
        popup.destroyed.connect(lambda: self._incoming_call_popups.pop(connection_id, None))
        stack_index = len(self._incoming_call_popups)
        self._incoming_call_popups[connection_id] = popup

        screen = QApplication.primaryScreen()
        margin = 16
        popup.adjustSize()
        if screen is not None:
            geometry = screen.availableGeometry()
            x = geometry.right() - popup.width() - margin
            y = geometry.bottom() - popup.height() - margin - stack_index * (
                popup.height() + margin
            )
            popup.move(x, y)
        popup.show()

    def _close_incoming_call_popup(self, connection_id: str) -> None:
        popup = self._incoming_call_popups.get(connection_id)
        if popup is not None:
            popup.close()

    def _update_all_calls_tab_label(self, count: int) -> None:
        label = f"Alle Anrufe ({count} neu verpasst)" if count else "Alle Anrufe"
        self._tabs.setTabText(0, label)

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
        self._tabs.setCurrentIndex(1)
        source_row = self._contact_model.index_of(contact_id)
        if source_row is not None:
            proxy_row = self._contact_proxy.mapFromSource(self._contact_model.index(source_row, 0)).row()
            self._table.selectRow(proxy_row)

    def _on_contact_table_double_clicked(self, index) -> None:
        if index.column() not in _CONTACT_PHONEBOOK_COLUMNS:
            return
        source_row = self._contact_proxy.mapToSource(index).row()
        contact = self._contact_model.contact_at(source_row)
        if contact.is_anonymous:
            return
        self._phonebook_tab.add_or_edit_number(contact.primary_number)

    def _contact_number_for_row(self, row: int) -> str | None:
        contact = self._contact_model.contact_at(row)
        return None if contact.is_anonymous else contact.primary_number

    def _dial_number(self, number: str) -> None:
        # _close_requested-Check aus demselben Grund wie in _trigger_sync():
        # ohne ihn koennte ein Rechtsklick kurz vor dem Schliessen noch einen
        # DialWorker starten, den closeEvent() (das den Schliessvorgang schon
        # eingeleitet hat) nicht mehr erwartet.
        if self._close_requested or self._dial_fn is None:
            if not self._close_requested:
                self.statusBar().showMessage(
                    "Anrufen nicht verfügbar (keine Zugangsdaten hinterlegt)", 5000
                )
            return
        if self._dial_thread is not None and self._dial_thread.isRunning():
            self.statusBar().showMessage("Es läuft bereits ein Anruf-Versuch …", 5000)
            return
        self.statusBar().showMessage(f"Rufe {number} an …")

        self._dial_thread = DialWorker(lambda: self._dial_fn(number), parent=self)
        self._dial_thread.dial_succeeded.connect(lambda: self._on_dial_succeeded(number))
        self._dial_thread.dial_failed.connect(self._on_dial_failed)
        self._dial_thread.start()

    def _on_dial_succeeded(self, number: str) -> None:
        self.statusBar().showMessage(f"Anruf ausgelöst: {number}", 5000)

    def _on_dial_failed(self, message: str) -> None:
        self.statusBar().showMessage(f"Anruf fehlgeschlagen: {message}", 8000)

    def _on_selection_changed(self, selected, deselected) -> None:
        indexes = selected.indexes()
        if not indexes:
            self._detail.clear()
            return
        source_row = self._contact_proxy.mapToSource(indexes[0]).row()
        contact = self._contact_model.contact_at(source_row)
        self._detail.show_contact(contact)

    def _trigger_sync(self) -> None:
        # _close_requested-Check ist noetig, weil der Start-Sync per
        # singleShot(0, ...) erst in einem spaeteren Event-Loop-Durchlauf
        # feuert - schliesst der Nutzer das Fenster, bevor dieser Zero-Delay-
        # Timer dran war, saehe closeEvent() noch keinen laufenden Thread und
        # wuerde sofort schliessen; der danach doch noch feuernde Sync wuerde
        # dann einen neuen, von niemandem mehr erwarteten SyncWorker starten,
        # der beim Interpreter-Shutdown wieder als laufender QThread zerstoert
        # wird (derselbe SIGABRT/Haenger wie beim urspruenglichen Bug).
        if (
            self._close_requested
            or self._sync_fn is None
            or (self._sync_thread is not None and self._sync_thread.isRunning())
        ):
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
        self._all_calls_view.clear_ended_live_calls()
        self._all_calls_view.reload()

    def _on_sync_failed(self, message: str) -> None:
        self._sync_button.setEnabled(True)
        self.statusBar().showMessage(f"Sync fehlgeschlagen: {message}", 8000)
