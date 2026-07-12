"""Hauptfenster: Kontaktliste (Name/Nummer/letzter Kontakt/Anzahl Anrufe),
Suche, Detailansicht und Sync-Aktion im Menü (im Hintergrund-Thread)."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Callable

from PySide6.QtCore import QThread, QTimer, Qt
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QMainWindow,
    QMessageBox,
    QStyle,
    QSystemTrayIcon,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from fritz_callhistory import config as config_module
from fritz_callhistory.config import Config
from fritz_callhistory.db.repository import ContactRepository, LocalPhonebookRepository
from fritz_callhistory.gui.calls_tab import CallsTab
from fritz_callhistory.gui.callmonitor_worker import CallMonitorThread
from fritz_callhistory.gui.credentials_dialog import CredentialsDialog
from fritz_callhistory.gui.incoming_call_popup import IncomingCallPopup
from fritz_callhistory.gui.phonebook_view import PhonebookTab
from fritz_callhistory.gui.settings_dialog import SettingsDialog
from fritz_callhistory.gui.voicemail_view import AudioFetchFn, VoicemailActionFn, VoicemailView
from fritz_callhistory.gui.workers import (
    DialFn,
    DialWorker,
    ImportFromBoxFn,
    ListPhonebooksFn,
    PhonebookListWorker,
    SyncFn,
    SyncWorker,
    TestCredentialsFn,
)
from fritz_callhistory.sync.normalize import format_number_display, normalize_number

# Letzte Absicherung für closeEvent(): SyncWorker/ImportFromBoxWorker haben
# in fritz/client.py zwar ein Netzwerk-Timeout, das deckt aber z.B. keinen
# hängenden DNS-Lookup ab (socket.getaddrinfo() kennt kein Timeout). Damit
# das Beenden trotzdem nie unbegrenzt hängen bleibt, wird nach dieser Frist
# hart abgebrochen, falls dann immer noch ein Worker-Thread läuft.
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
        voicemail_audio_fn: AudioFetchFn | None = None,
        voicemail_mark_read_fn: VoicemailActionFn | None = None,
        voicemail_delete_fn: VoicemailActionFn | None = None,
        config: Config | None = None,
        list_phonebooks_fn: ListPhonebooksFn | None = None,
        update_credentials_fn: Callable[[Config], None] | None = None,
        test_credentials_fn: TestCredentialsFn | None = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("Fritz!Box Anrufhistorie")
        self.resize(900, 600)

        self._sync_fn = sync_fn
        self._sync_thread: SyncWorker | None = None
        self._dial_fn = dial_fn
        self._dial_thread: DialWorker | None = None
        self._config = config or Config()
        self._list_phonebooks_fn = list_phonebooks_fn
        self._phonebook_list_thread: PhonebookListWorker | None = None
        self._close_requested = False
        self._shutdown_failsafe_timer: QTimer | None = None
        self._update_credentials_fn = update_credentials_fn
        self._test_credentials_fn = test_credentials_fn
        self._sync_auth_declined = False
        self._last_sync_user_initiated = False

        self._contacts_repo = ContactRepository(connection)
        self._local_phonebook_repo = LocalPhonebookRepository(connection)
        self._show_incoming_call_popup = show_incoming_call_popup
        self._incoming_call_popups: dict[str, IncomingCallPopup] = {}

        self._calls_tab = CallsTab(connection)
        self._calls_tab.new_missed_calls_changed.connect(self._on_new_missed_calls_changed)
        self._calls_tab.live_call_ended.connect(self._trigger_sync)
        self._calls_tab.call_requested.connect(self._dial_number)

        self._voicemail_view = VoicemailView(
            connection,
            audio_fetch_fn=voicemail_audio_fn,
            mark_read_fn=voicemail_mark_read_fn,
            delete_fn=voicemail_delete_fn,
        )
        self._voicemail_view.call_requested.connect(self._dial_number)
        self._voicemail_view.new_voicemail_count_changed.connect(
            self._on_new_voicemail_count_changed
        )

        self._phonebook_tab = PhonebookTab(connection, import_from_box_fn=import_from_box_fn)
        self._phonebook_tab.contacts_changed.connect(self._calls_tab.reload_contacts)
        self._phonebook_tab.call_requested.connect(self._dial_number)
        self._calls_tab.number_double_clicked.connect(self._phonebook_tab.add_or_edit_number)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._calls_tab, "Alle Anrufe")
        self._tabs.addTab(self._voicemail_view, "Anrufbeantworter")
        self._tabs.addTab(self._phonebook_tab, "Telefonbuch")
        # AllCallsView.__init__ (innerhalb CallsTab) hat _reload() bereits vor
        # der obigen Signal-Verbindung ausgeführt - die erste
        # new_missed_calls_changed-Emission kam daher ohne Empfänger an.
        # Deshalb hier einmalig den bereits berechneten, gecachten Wert direkt
        # abfragen statt nur aufs Signal zu vertrauen.
        self._update_all_calls_tab_label(self._calls_tab.new_missed_calls_count)
        self._update_voicemail_tab_label(self._voicemail_view.new_voicemail_count)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(self._tabs)
        self.setCentralWidget(central)
        self.statusBar()

        # Als self._xxx gehalten statt als lokale Variable: ohne eine
        # bleibende Python-Referenz hat sich das QMenu/QAction-Objekt in der
        # Praxis als vorzeitig von shiboken zerstört erwiesen (RuntimeError
        # "Internal C++ object already deleted"), obwohl es über die Qt-
        # Elternschaft (menuBar()) eigentlich am Leben gehalten werden sollte.
        self._sync_action = QAction("Jetzt synchronisieren", self)
        self._sync_action.setShortcut(QKeySequence("F5"))
        self._sync_action.triggered.connect(lambda: self._trigger_sync(user_initiated=True))
        self._sync_action.setEnabled(self._sync_fn is not None)

        self._settings_action = QAction("Einstellungen…", self)
        self._settings_action.triggered.connect(self._open_settings_dialog)
        self._credentials_action = QAction("Zugangsdaten ändern…", self)
        self._credentials_action.triggered.connect(self._open_credentials_dialog)
        self._file_menu = self.menuBar().addMenu("Datei")
        self._file_menu.addAction(self._sync_action)
        self._file_menu.addSeparator()
        self._file_menu.addAction(self._settings_action)
        self._file_menu.addAction(self._credentials_action)

        self._phonebook_import_action = QAction("Importieren …", self)
        self._phonebook_import_action.triggered.connect(self._phonebook_tab.import_from_file)
        self._phonebook_export_action = QAction("Exportieren …", self)
        self._phonebook_export_action.triggered.connect(self._phonebook_tab.export_to_file)
        self._phonebook_import_from_box_action = QAction("Von Box importieren …", self)
        self._phonebook_import_from_box_action.triggered.connect(self._phonebook_tab.import_from_box)
        self._phonebook_import_from_box_action.setEnabled(self._phonebook_tab.can_import_from_box)
        self._phonebook_tab.import_from_box_availability_changed.connect(
            self._phonebook_import_from_box_action.setEnabled
        )

        self._phonebook_menu = self.menuBar().addMenu("Telefonbuch")
        self._phonebook_menu.addAction(self._phonebook_import_action)
        self._phonebook_menu.addAction(self._phonebook_export_action)
        self._phonebook_menu.addSeparator()
        self._phonebook_menu.addAction(self._phonebook_import_from_box_action)

        if auto_sync_interval_minutes and self._sync_fn is not None:
            self._auto_sync_timer = QTimer(self)
            self._auto_sync_timer.setInterval(auto_sync_interval_minutes * 60 * 1000)
            self._auto_sync_timer.timeout.connect(self._trigger_sync)
            self._auto_sync_timer.start()

        # Verzögert per singleShot(0, ...) statt direktem Aufruf: so kehrt
        # __init__ zuerst zurück und das Fenster wird sichtbar, bevor der
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
            self._call_monitor.ring.connect(self._calls_tab.on_live_ring)
            self._call_monitor.connected.connect(self._calls_tab.on_live_connected)
            self._call_monitor.disconnected.connect(self._calls_tab.on_live_disconnected)
            self._call_monitor.connected.connect(self._close_incoming_call_popup)
            self._call_monitor.disconnected.connect(self._close_incoming_call_popup)
            self._call_monitor.connection_lost.connect(self._on_call_monitor_connection_lost)
            self._call_monitor.connection_lost.connect(self._calls_tab.clear_live_calls)
            self._call_monitor.start()

    def _busy_worker_threads(self) -> list[QThread]:
        """SyncWorker/ImportFromBoxWorker/DialWorker/VoicemailAudioWorker/
        VoicemailActionWorker führen einen einzelnen blockierenden Netzwerkaufruf
        ohne Abbruchpunkte aus - alle müssen hier erkannt werden, damit
        closeEvent() das Fenster nicht schliesst, während einer von ihnen noch
        läuft (siehe closeEvent() für die Begründung)."""
        threads: list[QThread] = []
        if self._sync_thread is not None and self._sync_thread.isRunning():
            threads.append(self._sync_thread)
        import_thread = self._phonebook_tab.import_thread
        if import_thread is not None and import_thread.isRunning():
            threads.append(import_thread)
        if self._dial_thread is not None and self._dial_thread.isRunning():
            threads.append(self._dial_thread)
        audio_thread = self._voicemail_view.audio_thread
        if audio_thread is not None and audio_thread.isRunning():
            threads.append(audio_thread)
        action_thread = self._voicemail_view.action_thread
        if action_thread is not None and action_thread.isRunning():
            threads.append(action_thread)
        return threads

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._close_requested:
            self._close_requested = True
            if self._call_monitor is not None:
                self._call_monitor.stop()

        # Ein festes wait(N) könnte ablaufen, während so ein Thread noch in
        # seinem HTTP-Request steckt, und Qt würde ihn beim Zerstören des
        # Fensters mit SIGABRT abbrechen. Stattdessen wird das Fenster nur
        # versteckt (wirkt für den Nutzer bereits geschlossen); sobald der
        # letzte betroffene Thread von selbst fertig ist, löst sein
        # finished-Signal close() erneut aus - dann ist die Liste leer und der
        # eigentliche Schliessvorgang läuft durch.
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
        # beenden"-Mechanismus) hat sich in der Praxis als nicht zuverlässig
        # herausgestellt, um app.exec() tatsächlich zurückkehren zu lassen -
        # vermutlich abhängig von Plattform/Compositor und dem hier immer
        # sichtbaren QSystemTrayIcon. Explizit quit() aufzurufen macht das
        # unabhängig davon; main() in app.py sorgt zusätzlich dafür, dass
        # der Prozess unmittelbar endet, sobald app.exec() zurückkehrt (statt
        # sich auf Pythons normale, langsamere Aufräum-Reihenfolge zu
        # verlassen).
        app_instance = QApplication.instance()
        if app_instance is not None:
            app_instance.quit()

    def _force_exit_if_still_busy(self) -> None:
        # Feuert nur, wenn ein Worker-Thread _SHUTDOWN_FAILSAFE_MS nach dem
        # ersten Schliessversuch immer noch läuft - regulär erfolgreiche
        # Sync-/Import-Vorgänge haben längst über ihr finished-Signal einen
        # erneuten, diesmal erfolgreichen close() ausgelöst und diese Methode
        # läuft dann entweder gar nicht mehr oder trifft auf eine leere Liste.
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
            message = (
                contact.display_name
                if (contact and contact.display_name)
                else format_number_display(normalized)
            )
            contact_id = contact.id if contact else None
            local_contact = self._local_phonebook_repo.find_by_number(normalized)
            notes = local_contact.notes if local_contact else None
        self._tray_icon.showMessage(
            "Eingehender Anruf", message, QSystemTrayIcon.MessageIcon.Information, 8000
        )
        if self._show_incoming_call_popup:
            self._show_incoming_call_window(
                connection_id,
                message,
                "" if is_anonymous else format_number_display(normalized),
                notes,
                contact_id,
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

    def _update_voicemail_tab_label(self, count: int) -> None:
        label = f"Anrufbeantworter ({count} neu)" if count else "Anrufbeantworter"
        self._tabs.setTabText(1, label)

    def _on_new_voicemail_count_changed(self, count: int) -> None:
        self._update_voicemail_tab_label(count)

    def _on_call_monitor_connection_lost(self, message: str) -> None:
        if self._call_monitor_connection_lost_shown:
            return
        self._call_monitor_connection_lost_shown = True
        self.statusBar().showMessage(
            "CallMonitor nicht erreichbar - ist der Wählcode #96*5* auf der Box aktiviert? "
            "(Verbindung wird automatisch weiter versucht.)",
            10000,
        )

    def _on_all_calls_contact_selected(self, contact_id: int) -> None:
        # Kann von jedem Tab aus ausgelöst werden (z.B. dem Popup bei einem
        # eingehenden Anruf) - deshalb hier explizit zurück auf "Alle Anrufe"
        # wechseln, statt vorauszusetzen, dass es schon aktiv ist.
        self._tabs.setCurrentIndex(0)
        self._calls_tab.show_contact(contact_id)

    def _dial_number(self, number: str) -> None:
        # _close_requested-Check aus demselben Grund wie in _trigger_sync():
        # ohne ihn könnte ein Rechtsklick kurz vor dem Schliessen noch einen
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
        self.statusBar().showMessage(f"Rufe {format_number_display(number)} an …")

        self._dial_thread = DialWorker(lambda: self._dial_fn(number), parent=self)
        self._dial_thread.dial_succeeded.connect(lambda: self._on_dial_succeeded(number))
        self._dial_thread.dial_failed.connect(self._on_dial_failed)
        self._dial_thread.start()

    def _open_settings_dialog(self) -> None:
        dialog = SettingsDialog(self._config, parent=self)
        if self._list_phonebooks_fn is None:
            dialog.set_phonebooks_unavailable("Keine Zugangsdaten hinterlegt")
        else:
            # An MainWindow (self), nicht am Dialog gehängt: der Dialog ist nur
            # so lange am Leben, wie exec() läuft, der Netzwerk-Fetch aber
            # kann bis zum Timeout dauern - schliesst der Nutzer den Dialog
            # vorher, würde ein am Dialog hängender QThread zerstört werden,
            # während er noch läuft (SIGABRT). An MainWindow gehängt läuft er
            # einfach im Hintergrund zu Ende; Qt trennt die Signal-Verbindung
            # zum dann bereits zerstörten Dialog automatisch.
            self._phonebook_list_thread = PhonebookListWorker(self._list_phonebooks_fn, parent=self)
            self._phonebook_list_thread.finished_listing.connect(dialog.set_phonebooks)
            self._phonebook_list_thread.listing_failed.connect(dialog.set_phonebooks_unavailable)
            self._phonebook_list_thread.start()

        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._config = dialog.save(self._config)
            QMessageBox.information(
                self,
                "Einstellungen gespeichert",
                "Die Änderungen werden erst nach einem Neustart der App wirksam.",
            )

    def _on_dial_succeeded(self, number: str) -> None:
        self.statusBar().showMessage(f"Anruf ausgelöst: {format_number_display(number)}", 5000)

    def _on_dial_failed(self, message: str) -> None:
        self.statusBar().showMessage(f"Anruf fehlgeschlagen: {message}", 8000)

    def _trigger_sync(self, user_initiated: bool = False) -> None:
        # _close_requested-Check ist nötig, weil der Start-Sync per
        # singleShot(0, ...) erst in einem späteren Event-Loop-Durchlauf
        # feuert - schliesst der Nutzer das Fenster, bevor dieser Zero-Delay-
        # Timer dran war, sähe closeEvent() noch keinen laufenden Thread und
        # würde sofort schliessen; der danach doch noch feuernde Sync würde
        # dann einen neuen, von niemandem mehr erwarteten SyncWorker starten,
        # der beim Interpreter-Shutdown wieder als laufender QThread zerstört
        # wird (derselbe SIGABRT/Hänger wie beim ursprünglichen Bug).
        if (
            self._close_requested
            or self._sync_fn is None
            or (self._sync_thread is not None and self._sync_thread.isRunning())
        ):
            return
        self._sync_action.setEnabled(False)
        self.statusBar().showMessage("Synchronisiere mit der Fritz!Box …")
        self._last_sync_user_initiated = user_initiated

        self._sync_thread = SyncWorker(self._sync_fn, parent=self)
        self._sync_thread.finished_sync.connect(self._on_sync_finished)
        self._sync_thread.sync_failed.connect(self._on_sync_failed)
        self._sync_thread.auth_failed.connect(self._on_sync_auth_failed)
        self._sync_thread.start()

    def _on_sync_finished(self, inserted: int, updated: int) -> None:
        self._sync_action.setEnabled(True)
        self._sync_auth_declined = False
        self.statusBar().showMessage(
            f"Sync abgeschlossen: {inserted} neue Anrufe, {updated} Kontakte aktualisiert", 5000
        )
        self._calls_tab.reload_contacts()
        self._calls_tab.clear_ended_live_calls()
        self._calls_tab.reload()
        self._voicemail_view.reload()

    def _on_sync_failed(self, message: str) -> None:
        self._sync_action.setEnabled(True)
        self.statusBar().showMessage(f"Sync fehlgeschlagen: {message}", 8000)

    def _on_sync_auth_failed(self, message: str) -> None:
        # Nur bei einem manuell ausgelösten Sync (F5) oder wenn der Nutzer den
        # Dialog beim letzten automatischen Fehlschlag noch nicht abgelehnt
        # hat, wird der Dialog erneut gezeigt - sonst würde der Auto-Sync-Timer
        # (alle sync_interval_minutes) den Dialog endlos erneut aufpoppen,
        # solange die Zugangsdaten falsch bleiben.
        self._sync_action.setEnabled(True)
        if not self._last_sync_user_initiated and self._sync_auth_declined:
            self.statusBar().showMessage(
                f"Sync fehlgeschlagen: Zugangsdaten prüfen ({message})", 8000
            )
            return

        QMessageBox.warning(
            self,
            "Anmeldung fehlgeschlagen",
            "Benutzername oder Passwort für die Fritz!Box sind falsch. "
            "Bitte Zugangsdaten prüfen.",
        )
        dialog = CredentialsDialog(
            config_module.load(), test_connection_fn=self._test_credentials_fn, parent=self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_config = dialog.save(config_module.load())
            self._config = new_config
            if self._update_credentials_fn is not None:
                self._update_credentials_fn(new_config)
            self._sync_auth_declined = False
            self._trigger_sync(user_initiated=True)
        else:
            self._sync_auth_declined = True
            self.statusBar().showMessage("Sync fehlgeschlagen: Zugangsdaten nicht geändert", 8000)

    def _open_credentials_dialog(self) -> None:
        dialog = CredentialsDialog(
            config_module.load(), test_connection_fn=self._test_credentials_fn, parent=self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_config = dialog.save(config_module.load())
            self._config = new_config
            if self._update_credentials_fn is not None:
                self._update_credentials_fn(new_config)
            self._sync_auth_declined = False
            self.statusBar().showMessage("Zugangsdaten gespeichert.", 5000)
