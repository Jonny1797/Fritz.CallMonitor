import threading

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QPushButton

from fritz_callhistory.config import Config
from fritz_callhistory.db.repository import CallRepository, ContactRepository, SyncStateRepository
from fritz_callhistory.fritz.exceptions import FritzBoxConnectionError
from fritz_callhistory.gui.all_calls_view import _LAST_SEEN_KEY
from fritz_callhistory.gui.main_window import MainWindow


def test_contact_table_and_call_table_are_direct_splitter_children(qtbot, connection):
    # Beide Tabellen sind der alleinige Inhalt ihres jeweiligen Splitter-Kinds
    # (kein interner Header mehr, der eine Tabelle kürzer macht als die
    # andere) - der Splitter gibt beiden Kindern dieselbe Gesamthöhe, also
    # enden beide Tabellen automatisch gleich hoch.
    window = MainWindow(connection)
    qtbot.addWidget(window)

    assert window._table.parentWidget() is window._detail.parentWidget()


def test_contact_detail_labels_shown_in_full_width_header_above_splitter(qtbot, connection):
    contacts = ContactRepository(connection)
    contact_id = contacts.upsert("+491234567")
    contacts.set_display_name(contact_id, "Max Mustermann")

    window = MainWindow(connection)
    qtbot.addWidget(window)
    window._table.selectRow(0)

    assert "Max Mustermann" in window._detail.title_label.text()
    # Kein Splitter-Kind mehr - liegt jetzt oberhalb, als Geschwister des Splitters.
    assert window._detail.title_label.parentWidget() is not window._detail


def test_contact_table_sorting_cycles_and_selection_still_resolves(qtbot, connection):
    contacts = ContactRepository(connection)
    id_a = contacts.upsert("+491111111")
    contacts.set_display_name(id_a, "Bertha")
    id_b = contacts.upsert("+492222222")
    contacts.set_display_name(id_b, "Anton")

    window = MainWindow(connection)
    qtbot.addWidget(window)
    header = window._table.horizontalHeader()

    header.sectionClicked.emit(0)  # Name aufsteigend
    assert window._contact_proxy.data(window._contact_proxy.index(0, 0)) == "Anton"

    window._table.selectRow(0)
    assert "Anton" in window._detail._title_label.text()

    header.sectionClicked.emit(0)  # absteigend
    header.sectionClicked.emit(0)  # zurück zur Ausgangsreihenfolge

    assert window._contact_proxy.data(window._contact_proxy.index(0, 0)) == "Bertha"


def test_selecting_from_all_calls_resolves_correct_row_while_sorted(qtbot, connection):
    contacts = ContactRepository(connection)
    id_a = contacts.upsert("+491111111")
    contacts.set_display_name(id_a, "Bertha")
    id_b = contacts.upsert("+492222222")
    contacts.set_display_name(id_b, "Anton")

    window = MainWindow(connection)
    qtbot.addWidget(window)
    window._table.horizontalHeader().sectionClicked.emit(0)  # Name aufsteigend

    window._all_calls_view.contact_selected.emit(id_a)

    assert "Bertha" in window._detail._title_label.text()


def test_main_window_shows_seeded_contacts(qtbot, connection):
    contacts = ContactRepository(connection)
    contacts.upsert("+491234567")
    contact_id = contacts.upsert("+499876543")
    contacts.set_display_name(contact_id, "Max Mustermann")

    window = MainWindow(connection)
    qtbot.addWidget(window)

    model = window._contact_model
    assert model.rowCount() == 2
    names = {model.contact_at(row).primary_number for row in range(model.rowCount())}
    assert names == {"+491234567", "+499876543"}


def test_main_window_reload_picks_up_new_contacts(qtbot, connection):
    window = MainWindow(connection)
    qtbot.addWidget(window)
    assert window._contact_model.rowCount() == 0

    ContactRepository(connection).upsert("+491234567")
    window.reload_contacts()

    assert window._contact_model.rowCount() == 1


def test_search_filters_by_name_and_number(qtbot, connection):
    contacts = ContactRepository(connection)
    contact_id = contacts.upsert("+491234567")
    contacts.set_display_name(contact_id, "Max Mustermann")
    contacts.upsert("+499876543")

    window = MainWindow(connection)
    qtbot.addWidget(window)
    assert window._contact_model.rowCount() == 2

    window._search_edit.setText("Mustermann")
    qtbot.wait(400)

    assert window._contact_model.rowCount() == 1
    assert window._contact_model.contact_at(0).primary_number == "+491234567"


def test_search_by_number_fragment(qtbot, connection):
    contacts = ContactRepository(connection)
    contacts.upsert("+491234567")
    contacts.upsert("+499876543")

    window = MainWindow(connection)
    qtbot.addWidget(window)

    window._search_edit.setText("9876543")
    qtbot.wait(400)

    assert window._contact_model.rowCount() == 1
    assert window._contact_model.contact_at(0).primary_number == "+499876543"


def test_clearing_search_shows_all_contacts_again(qtbot, connection):
    contacts = ContactRepository(connection)
    contacts.upsert("+491234567")
    contacts.upsert("+499876543")

    window = MainWindow(connection)
    qtbot.addWidget(window)

    window._search_edit.setText("1234567")
    qtbot.wait(400)
    assert window._contact_model.rowCount() == 1

    window._search_edit.setText("")
    qtbot.wait(400)
    assert window._contact_model.rowCount() == 2


def test_selecting_row_shows_contact_detail(qtbot, connection):
    contacts = ContactRepository(connection)
    contact_id = contacts.upsert("+491234567")
    contacts.set_display_name(contact_id, "Max Mustermann")
    CallRepository(connection).insert(
        contact_id=contact_id,
        call_type=1,
        caller_number="+491234567",
        called_number=None,
        port="1",
        device="Fritz!Fon",
        call_date="2026-06-01T10:00:00",
        duration_seconds=30,
        raw_name=None,
    )

    window = MainWindow(connection)
    qtbot.addWidget(window)

    window._table.selectRow(0)

    assert "Max Mustermann" in window._detail._title_label.text()
    assert window._detail._call_model.rowCount() == 1


def test_search_reset_clears_detail_view(qtbot, connection):
    contacts = ContactRepository(connection)
    contact_id = contacts.upsert("+491234567")
    contacts.set_display_name(contact_id, "Max Mustermann")

    window = MainWindow(connection)
    qtbot.addWidget(window)
    window._table.selectRow(0)
    assert "Max Mustermann" in window._detail._title_label.text()

    window._search_edit.setText("kein-treffer-xyz")
    qtbot.wait(400)

    assert window._detail._title_label.text() == "Wählen Sie einen Kontakt aus, um mehr Details zu sehen."


def test_sync_button_disabled_without_sync_fn(qtbot, connection):
    window = MainWindow(connection)
    qtbot.addWidget(window)

    assert not window._sync_button.isEnabled()


def test_sync_button_updates_status_bar_and_reloads_on_success(qtbot, connection):
    window = MainWindow(connection, sync_fn=lambda: (2, 1))
    qtbot.addWidget(window)
    assert window._sync_button.isEnabled()

    window._sync_button.click()
    assert not window._sync_button.isEnabled()

    qtbot.waitUntil(lambda: "abgeschlossen" in window.statusBar().currentMessage(), timeout=3000)

    assert "2 neue Anrufe" in window.statusBar().currentMessage()
    assert window._sync_button.isEnabled()


def test_sync_runs_automatically_on_startup(qtbot, connection):
    window = MainWindow(connection, sync_fn=lambda: (2, 1))
    qtbot.addWidget(window)

    qtbot.waitUntil(lambda: "abgeschlossen" in window.statusBar().currentMessage(), timeout=3000)

    assert "2 neue Anrufe" in window.statusBar().currentMessage()


def test_sync_finished_clears_ended_live_calls(qtbot, connection):
    window = MainWindow(connection, sync_fn=lambda: (0, 0))
    qtbot.addWidget(window)
    window._all_calls_view.on_live_ring("1", "030 1234567", "069987654")
    window._all_calls_view.on_live_disconnected("1")
    assert window._all_calls_view._model.rowCount() == 1

    window._sync_button.click()
    qtbot.waitUntil(lambda: "abgeschlossen" in window.statusBar().currentMessage(), timeout=3000)

    assert window._all_calls_view._model.rowCount() == 0


def test_sync_button_shows_error_on_failure(qtbot, connection):
    def failing_sync():
        raise FritzBoxConnectionError("Box nicht erreichbar")

    window = MainWindow(connection, sync_fn=failing_sync)
    qtbot.addWidget(window)

    window._sync_button.click()
    qtbot.waitUntil(lambda: "fehlgeschlagen" in window.statusBar().currentMessage(), timeout=3000)

    assert "Box nicht erreichbar" in window.statusBar().currentMessage()
    assert window._sync_button.isEnabled()


def test_close_while_sync_running_defers_until_sync_finishes(qtbot, connection):
    # Regression test: sync_fn (SyncWorker) is a single blocking network call
    # with no cancellation point. closeEvent() used to just wait(2000) and then
    # proceed regardless - if the sync (auto-triggered on startup) was still
    # running past that timeout, the still-running QThread got destroyed and
    # Qt aborted the process with SIGABRT. closeEvent() must instead hide the
    # window and defer the real close until the thread finishes on its own.
    release_sync = threading.Event()

    def slow_sync():
        release_sync.wait(5)
        return (0, 0)

    window = MainWindow(connection, sync_fn=slow_sync)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(
        lambda: window._sync_thread is not None and window._sync_thread.isRunning(), timeout=2000
    )

    closed = window.close()

    assert closed is False  # close event was ignored, not accepted
    assert not window.isVisible()  # hidden immediately so it looks closed
    assert window._sync_thread.isRunning()  # thread left running untouched, not destroyed

    release_sync.set()
    qtbot.waitUntil(lambda: not window._sync_thread.isRunning(), timeout=2000)
    qtbot.wait(50)  # let the queued finished-signal-triggered close() run

    # Thread is done now - a subsequent close attempt goes through immediately.
    assert window.close() is True


def test_shutdown_failsafe_force_exits_if_worker_still_busy(qtbot, connection, mocker):
    # Regression test: fritz/client.py's request timeout doesn't cover every
    # possible hang (e.g. a blocking DNS lookup, which socket.getaddrinfo()
    # has no timeout for) - closeEvent()'s hide-and-wait-for-finished
    # mechanism must not be able to block forever if a worker thread never
    # returns. The failsafe timer (normally _SHUTDOWN_FAILSAFE_MS after the
    # first close attempt) must force an exit once it fires while still busy.
    release_sync = threading.Event()

    def slow_sync():
        release_sync.wait(5)
        return (0, 0)

    window = MainWindow(connection, sync_fn=slow_sync)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(
        lambda: window._sync_thread is not None and window._sync_thread.isRunning(), timeout=2000
    )
    window.close()
    assert window._shutdown_failsafe_timer is not None

    force_exit = mocker.patch("fritz_callhistory.gui.main_window.os._exit")
    window._force_exit_if_still_busy()
    force_exit.assert_called_once_with(1)

    release_sync.set()  # cleanup: let the thread actually finish
    qtbot.waitUntil(lambda: not window._sync_thread.isRunning(), timeout=2000)


def test_shutdown_failsafe_does_nothing_once_worker_already_finished(qtbot, connection, mocker):
    window = MainWindow(connection, sync_fn=lambda: (0, 0))
    qtbot.addWidget(window)
    window.show()
    qtbot.waitUntil(lambda: "abgeschlossen" in window.statusBar().currentMessage(), timeout=3000)

    force_exit = mocker.patch("fritz_callhistory.gui.main_window.os._exit")
    window._force_exit_if_still_busy()

    force_exit.assert_not_called()


def test_close_before_startup_sync_fires_prevents_new_sync_thread(qtbot, connection):
    # Regression test: the auto-sync at startup is queued via
    # QTimer.singleShot(0, self._trigger_sync), which only runs on a later
    # event-loop iteration. Closing the window before that fires must prevent
    # _trigger_sync() from starting a brand-new, untracked SyncWorker
    # afterwards - otherwise it becomes a QThread nobody waits for at
    # interpreter shutdown (the same crash/hang class, just with different
    # timing - reproduced within the app's very first instant instead of a
    # few seconds in).
    window = MainWindow(connection, sync_fn=lambda: (0, 0))
    qtbot.addWidget(window)
    window.show()

    assert window._sync_thread is None
    closed = window.close()
    assert closed is True  # nothing was running yet, closes immediately

    qtbot.wait(100)  # let the queued singleShot(0, _trigger_sync) fire, if it still would

    assert window._sync_thread is None


def test_close_while_box_import_running_defers_until_import_finishes(qtbot, connection, mocker):
    # Same bug class as test_close_while_sync_running_defers_until_sync_finishes,
    # but for ImportFromBoxWorker (the "Von Box importieren" button) - it is the
    # same single-blocking-network-call-with-no-cancellation-point pattern, just
    # user-triggered instead of started automatically on startup.
    release_import = threading.Event()

    def slow_import():
        release_import.wait(5)
        return 0

    mocker.patch(
        "fritz_callhistory.gui.phonebook_view.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Yes,
    )
    mocker.patch("fritz_callhistory.gui.phonebook_view.QMessageBox.information")

    window = MainWindow(connection, import_from_box_fn=slow_import)
    qtbot.addWidget(window)
    window.show()
    window._phonebook_tab._on_import_from_box_clicked()
    qtbot.waitUntil(
        lambda: window._phonebook_tab.import_thread is not None
        and window._phonebook_tab.import_thread.isRunning(),
        timeout=2000,
    )

    closed = window.close()

    assert closed is False
    assert not window.isVisible()
    assert window._phonebook_tab.import_thread.isRunning()

    release_import.set()
    qtbot.waitUntil(lambda: not window._phonebook_tab.import_thread.isRunning(), timeout=2000)
    qtbot.wait(50)

    assert window.close() is True


def test_close_without_busy_workers_quits_application_explicitly(qtbot, connection, mocker):
    # Regression test: relying purely on Qt's quitOnLastWindowClosed to end
    # app.exec() has proven unreliable in practice (window closes but the
    # process never terminates - suspected cause: the always-visible
    # QSystemTrayIcon, whose native backend can prevent the implicit quit
    # depending on platform/compositor). closeEvent() must explicitly call
    # QApplication.quit() itself once nothing is left running, instead of
    # just accepting the close event and hoping Qt notices.
    window = MainWindow(connection)
    qtbot.addWidget(window)
    window.show()

    quit_spy = mocker.patch.object(QApplication.instance(), "quit")

    assert window.close() is True

    quit_spy.assert_called_once()


def test_no_call_monitor_started_without_address(qtbot, connection):
    window = MainWindow(connection)
    qtbot.addWidget(window)

    assert window._call_monitor is None


def test_on_ring_shows_known_contact_name(qtbot, connection, mocker):
    contacts = ContactRepository(connection)
    contact_id = contacts.upsert("+49301234567")
    contacts.set_display_name(contact_id, "Max Mustermann")

    window = MainWindow(connection)
    qtbot.addWidget(window)
    show_message = mocker.patch.object(window._tray_icon, "showMessage")

    window._on_ring("0", "030 1234567", "069987654")

    show_message.assert_called_once()
    args = show_message.call_args.args
    assert args[0] == "Eingehender Anruf"
    assert args[1] == "Max Mustermann"

    popup = window._incoming_call_popups["0"]
    assert popup.connection_id == "0"


def test_on_ring_shows_number_for_unknown_contact(qtbot, connection, mocker):
    window = MainWindow(connection)
    qtbot.addWidget(window)
    show_message = mocker.patch.object(window._tray_icon, "showMessage")

    window._on_ring("0", "030 1234567", "069987654")

    args = show_message.call_args.args
    assert args[1] == "+49301234567"


def test_on_ring_shows_anonymous_for_suppressed_number(qtbot, connection, mocker):
    window = MainWindow(connection)
    qtbot.addWidget(window)
    show_message = mocker.patch.object(window._tray_icon, "showMessage")

    window._on_ring("0", "", "069987654")

    args = show_message.call_args.args
    assert "unterdrückt" in args[1] or "Unbekannt" in args[1]


def test_on_ring_popup_disabled_via_config_flag(qtbot, connection, mocker):
    window = MainWindow(connection, show_incoming_call_popup=False)
    qtbot.addWidget(window)
    mocker.patch.object(window._tray_icon, "showMessage")

    window._on_ring("0", "030 1234567", "069987654")

    assert window._incoming_call_popups == {}


def test_on_ring_popup_has_no_contact_action_for_anonymous_caller(qtbot, connection, mocker):
    window = MainWindow(connection)
    qtbot.addWidget(window)
    mocker.patch.object(window._tray_icon, "showMessage")

    window._on_ring("0", "", "069987654")

    popup = window._incoming_call_popups["0"]
    button_labels = [button.text() for button in popup.findChildren(QPushButton)]
    assert "Kontakt anzeigen" not in button_labels
    assert "Schließen" in button_labels


def test_connected_signal_closes_matching_popup(qtbot, connection, mocker):
    window = MainWindow(connection)
    qtbot.addWidget(window)
    mocker.patch.object(window._tray_icon, "showMessage")

    window._on_ring("0", "030 1234567", "069987654")
    popup = window._incoming_call_popups["0"]

    window._close_incoming_call_popup("0")
    assert popup.isVisible() is False
    qtbot.waitUntil(lambda: "0" not in window._incoming_call_popups, timeout=1000)


def test_disconnected_signal_closes_matching_popup(qtbot, connection, mocker):
    window = MainWindow(connection)
    qtbot.addWidget(window)
    mocker.patch.object(window._tray_icon, "showMessage")

    window._on_ring("0", "030 1234567", "069987654")

    window._close_incoming_call_popup("0")
    qtbot.waitUntil(lambda: "0" not in window._incoming_call_popups, timeout=1000)


def test_close_incoming_call_popup_ignores_unknown_connection_id(qtbot, connection):
    window = MainWindow(connection)
    qtbot.addWidget(window)

    window._close_incoming_call_popup("does-not-exist")  # muss nicht (mit KeyError) crashen


def test_two_simultaneous_calls_get_independent_popups(qtbot, connection, mocker):
    window = MainWindow(connection)
    qtbot.addWidget(window)
    mocker.patch.object(window._tray_icon, "showMessage")

    window._on_ring("0", "030 1234567", "069987654")
    window._on_ring("1", "030 7654321", "069987654")

    assert set(window._incoming_call_popups) == {"0", "1"}

    window._close_incoming_call_popup("0")
    qtbot.waitUntil(lambda: "0" not in window._incoming_call_popups, timeout=1000)
    assert "1" in window._incoming_call_popups


def test_open_contact_requested_navigates_to_contact(qtbot, connection, mocker):
    contacts = ContactRepository(connection)
    contact_id = contacts.upsert("+49301234567")
    contacts.set_display_name(contact_id, "Max Mustermann")

    window = MainWindow(connection)
    qtbot.addWidget(window)
    mocker.patch.object(window._tray_icon, "showMessage")

    window._on_ring("0", "030 1234567", "069987654")
    popup = window._incoming_call_popups["0"]
    window._tabs.setCurrentIndex(0)

    popup.open_contact_requested.emit(contact_id)

    assert window._tabs.currentIndex() == 2
    assert window._table.selectionModel().selectedRows()[0].row() == 0


def test_call_monitor_connection_lost_message_shown_only_once(qtbot, connection):
    window = MainWindow(connection)
    qtbot.addWidget(window)

    window._on_call_monitor_connection_lost("Connection refused")
    assert "#96*5*" in window.statusBar().currentMessage()

    window.statusBar().clearMessage()
    window._on_call_monitor_connection_lost("Connection refused again")
    assert window.statusBar().currentMessage() == ""


def test_main_window_has_four_tabs(qtbot, connection):
    window = MainWindow(connection)
    qtbot.addWidget(window)

    assert window._tabs.count() == 4
    assert window._tabs.tabText(0) == "Alle Anrufe"
    assert window._tabs.tabText(1) == "Anrufbeantworter"
    assert window._tabs.tabText(2) == "Kontakte"
    assert window._tabs.tabText(3) == "Telefonbuch"


def test_existing_widgets_still_reachable_after_tab_refactor(qtbot, connection):
    contacts = ContactRepository(connection)
    contacts.upsert("+491234567")

    window = MainWindow(connection)
    qtbot.addWidget(window)

    assert window._contact_model.rowCount() == 1
    window._search_edit.setText("kein-treffer")
    window._search_timer.timeout.emit()
    assert window._contact_model.rowCount() == 0
    assert window._sync_button.isEnabled() is False  # kein sync_fn übergeben


def test_clicking_call_in_all_calls_view_switches_tab_and_selects_contact(qtbot, connection):
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_id = contacts.upsert("+491234567")
    contacts.set_display_name(contact_id, "Max Mustermann")
    calls.insert(
        contact_id=contact_id,
        call_type=1,
        caller_number="+491234567",
        called_number=None,
        port="1",
        device="Fritz!Fon",
        call_date="2026-06-01T10:00:00",
        duration_seconds=30,
        raw_name=None,
    )

    window = MainWindow(connection)
    qtbot.addWidget(window)

    window._all_calls_view.contact_selected.emit(contact_id)

    assert window._tabs.currentIndex() == 2
    assert "Max Mustermann" in window._detail._title_label.text()


def test_navigation_from_all_calls_clears_active_search_filter(qtbot, connection):
    contacts = ContactRepository(connection)
    contact_id = contacts.upsert("+491234567")
    contacts.set_display_name(contact_id, "Max Mustermann")

    window = MainWindow(connection)
    qtbot.addWidget(window)
    window._search_edit.setText("passt-nicht-zu-max")
    window._search_timer.timeout.emit()
    assert window._contact_model.rowCount() == 0

    window._all_calls_view.contact_selected.emit(contact_id)

    assert window._search_edit.text() == ""
    assert window._contact_model.rowCount() == 1
    assert "Max Mustermann" in window._detail._title_label.text()


def test_all_calls_tab_label_shows_new_missed_count_on_startup(qtbot, connection):
    SyncStateRepository(connection).set(_LAST_SEEN_KEY, "2026-06-01T00:00:00")
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_id = contacts.upsert("+491234567")
    calls.insert(
        contact_id=contact_id,
        call_type=2,
        caller_number="+491234567",
        called_number=None,
        port="1",
        device="Fritz!Fon",
        call_date="2026-06-05T10:00:00",
        duration_seconds=0,
        raw_name=None,
    )

    window = MainWindow(connection)
    qtbot.addWidget(window)

    assert window._tabs.tabText(0) == "Alle Anrufe (1 neu verpasst)"


def test_all_calls_tab_label_stays_plain_when_no_new_missed_calls(qtbot, connection):
    window = MainWindow(connection)
    qtbot.addWidget(window)

    assert window._tabs.tabText(0) == "Alle Anrufe"


def test_all_calls_tab_label_updates_after_manual_reload(qtbot, connection):
    SyncStateRepository(connection).set(_LAST_SEEN_KEY, "2026-06-01T00:00:00")
    window = MainWindow(connection)
    qtbot.addWidget(window)
    assert window._tabs.tabText(0) == "Alle Anrufe"

    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_id = contacts.upsert("+491234567")
    calls.insert(
        contact_id=contact_id,
        call_type=2,
        caller_number="+491234567",
        called_number=None,
        port="1",
        device="Fritz!Fon",
        call_date="2026-06-05T10:00:00",
        duration_seconds=0,
        raw_name=None,
    )
    window._all_calls_view.reload()

    assert window._tabs.tabText(0) == "Alle Anrufe (1 neu verpasst)"


def test_live_call_ended_triggers_sync(qtbot, connection):
    window = MainWindow(connection, sync_fn=lambda: (0, 0))
    qtbot.addWidget(window)

    window._all_calls_view.live_call_ended.emit()

    qtbot.waitUntil(lambda: "abgeschlossen" in window.statusBar().currentMessage(), timeout=3000)


def test_call_monitor_signals_wired_to_all_calls_view(qtbot, connection, mocker):
    mock_thread_cls = mocker.patch("fritz_callhistory.gui.main_window.CallMonitorThread")
    mock_thread = mock_thread_cls.return_value

    window = MainWindow(connection, fritzbox_address="192.168.178.1")
    qtbot.addWidget(window)

    assert window._call_monitor is mock_thread
    mock_thread.ring.connect.assert_any_call(window._on_ring)
    mock_thread.ring.connect.assert_any_call(window._all_calls_view.on_live_ring)
    mock_thread.connected.connect.assert_any_call(window._all_calls_view.on_live_connected)
    mock_thread.disconnected.connect.assert_any_call(window._all_calls_view.on_live_disconnected)
    mock_thread.connected.connect.assert_any_call(window._close_incoming_call_popup)
    mock_thread.disconnected.connect.assert_any_call(window._close_incoming_call_popup)
    mock_thread.connection_lost.connect.assert_any_call(window._on_call_monitor_connection_lost)
    mock_thread.connection_lost.connect.assert_any_call(window._all_calls_view.clear_live_calls)
    mock_thread.start.assert_called_once()


def test_double_clicking_contact_number_column_offers_to_add_to_phonebook(qtbot, connection, mocker):
    contacts = ContactRepository(connection)
    contacts.upsert("+491234567")

    window = MainWindow(connection)
    qtbot.addWidget(window)
    add_or_edit = mocker.patch.object(window._phonebook_tab, "add_or_edit_number")

    window._on_contact_table_double_clicked(window._contact_model.index(0, 1))

    add_or_edit.assert_called_once_with("+491234567")


def test_double_clicking_contact_name_column_offers_to_add_to_phonebook(qtbot, connection, mocker):
    contacts = ContactRepository(connection)
    contacts.upsert("+491234567")

    window = MainWindow(connection)
    qtbot.addWidget(window)
    add_or_edit = mocker.patch.object(window._phonebook_tab, "add_or_edit_number")

    window._on_contact_table_double_clicked(window._contact_model.index(0, 0))

    add_or_edit.assert_called_once_with("+491234567")


def test_double_clicking_contact_other_columns_does_nothing(qtbot, connection, mocker):
    contacts = ContactRepository(connection)
    contact_id = contacts.upsert("+491234567")
    CallRepository(connection).insert(
        contact_id=contact_id,
        call_type=1,
        caller_number="+491234567",
        called_number=None,
        port="1",
        device="Fritz!Fon",
        call_date="2026-06-01T10:00:00",
        duration_seconds=30,
        raw_name=None,
    )

    window = MainWindow(connection)
    qtbot.addWidget(window)
    add_or_edit = mocker.patch.object(window._phonebook_tab, "add_or_edit_number")

    window._on_contact_table_double_clicked(window._contact_model.index(0, 2))
    window._on_contact_table_double_clicked(window._contact_model.index(0, 3))

    add_or_edit.assert_not_called()


def test_double_clicking_call_detail_number_offers_to_add_to_phonebook(qtbot, connection, mocker):
    contacts = ContactRepository(connection)
    contact_id = contacts.upsert("+491234567")
    CallRepository(connection).insert(
        contact_id=contact_id,
        call_type=1,
        caller_number="+491234567",
        called_number=None,
        port="1",
        device="Fritz!Fon",
        call_date="2026-06-01T10:00:00",
        duration_seconds=30,
        raw_name=None,
    )

    window = MainWindow(connection)
    qtbot.addWidget(window)
    window._table.selectRow(0)
    add_or_edit = mocker.patch.object(window._phonebook_tab, "add_or_edit_number")

    window._detail._call_table.doubleClicked.emit(window._detail._call_model.index(0, 2))

    add_or_edit.assert_called_once_with("+491234567")


def test_double_clicking_all_calls_row_navigates_to_kontakte(qtbot, connection):
    contacts = ContactRepository(connection)
    contact_id = contacts.upsert("+491234567")
    contacts.set_display_name(contact_id, "Max Mustermann")
    CallRepository(connection).insert(
        contact_id=contact_id,
        call_type=1,
        caller_number="+491234567",
        called_number=None,
        port="1",
        device="Fritz!Fon",
        call_date="2026-06-01T10:00:00",
        duration_seconds=30,
        raw_name=None,
    )

    window = MainWindow(connection)
    qtbot.addWidget(window)
    window._all_calls_view.reload()

    window._all_calls_view._table.doubleClicked.emit(window._all_calls_view._model.index(0, 2))

    assert window._tabs.currentIndex() == 2
    assert "Max Mustermann" in window._detail._title_label.text()


def test_contact_number_for_row_returns_primary_number(qtbot, connection):
    contacts = ContactRepository(connection)
    contacts.upsert("+491234567")

    window = MainWindow(connection)
    qtbot.addWidget(window)

    assert window._contact_number_for_row(0) == "+491234567"


def test_contact_number_for_row_returns_none_for_anonymous_contact(qtbot, connection):
    contacts = ContactRepository(connection)
    contacts.upsert("anonymous", is_anonymous=True)

    window = MainWindow(connection)
    qtbot.addWidget(window)

    assert window._contact_number_for_row(0) is None


def test_dial_number_shows_unavailable_message_without_dial_fn(qtbot, connection):
    window = MainWindow(connection)
    qtbot.addWidget(window)

    window._dial_number("+491234567")

    assert "nicht verfügbar" in window.statusBar().currentMessage()
    assert window._dial_thread is None


def test_dial_number_shows_success_message_and_calls_dial_fn(qtbot, connection):
    dialed = []
    window = MainWindow(connection, dial_fn=dialed.append)
    qtbot.addWidget(window)

    window._dial_number("+491234567")

    qtbot.waitUntil(lambda: "ausgelöst" in window.statusBar().currentMessage(), timeout=2000)
    assert dialed == ["+491234567"]
    assert "+491234567" in window.statusBar().currentMessage()


def test_phonebook_tab_call_requested_is_wired_to_dial_number(qtbot, connection):
    dialed = []
    window = MainWindow(connection, dial_fn=dialed.append)
    qtbot.addWidget(window)

    window._phonebook_tab.call_requested.emit("+491234567")

    qtbot.waitUntil(lambda: dialed == ["+491234567"], timeout=2000)


def test_dial_number_shows_error_on_failure(qtbot, connection):
    def failing_dial_fn(number):
        raise FritzBoxConnectionError("Box nicht erreichbar")

    window = MainWindow(connection, dial_fn=failing_dial_fn)
    qtbot.addWidget(window)

    window._dial_number("+491234567")

    qtbot.waitUntil(lambda: "fehlgeschlagen" in window.statusBar().currentMessage(), timeout=2000)
    assert "Box nicht erreichbar" in window.statusBar().currentMessage()


def test_dial_number_ignores_second_call_while_one_in_flight(qtbot, connection):
    # release_dial.set() must run even if an assertion below fails - otherwise
    # the DialWorker is still blocked in its network call when qtbot tears the
    # window down at test end, and Qt aborts the process (SIGABRT) trying to
    # destroy a still-running QThread (same bug class as
    # test_close_while_sync_running_defers_until_sync_finishes, just in test code).
    release_dial = threading.Event()
    calls = []

    def slow_dial(number):
        calls.append(number)
        release_dial.wait(5)

    window = MainWindow(connection, dial_fn=slow_dial)
    qtbot.addWidget(window)

    try:
        window._dial_number("+491111111")
        # isRunning() flips True before slow_dial's first line actually runs -
        # wait on the observable side effect itself, not the thread's state.
        qtbot.waitUntil(lambda: len(calls) == 1, timeout=2000)
        window._dial_number("+492222222")

        assert calls == ["+491111111"]
        assert "läuft bereits" in window.statusBar().currentMessage()
    finally:
        release_dial.set()
        qtbot.waitUntil(
            lambda: window._dial_thread is None or not window._dial_thread.isRunning(), timeout=2000
        )


def test_close_while_dial_running_defers_until_dial_finishes(qtbot, connection):
    # Same bug class as test_close_while_sync_running_defers_until_sync_finishes,
    # but for DialWorker - a right-click "Anrufen" triggers exactly the same
    # single-blocking-network-call-with-no-cancellation-point pattern.
    release_dial = threading.Event()

    def slow_dial(number):
        release_dial.wait(5)

    window = MainWindow(connection, dial_fn=slow_dial)
    qtbot.addWidget(window)
    window.show()
    try:
        window._dial_number("+491234567")
        qtbot.waitUntil(
            lambda: window._dial_thread is not None and window._dial_thread.isRunning(), timeout=2000
        )

        closed = window.close()

        assert closed is False
        assert not window.isVisible()
        assert window._dial_thread.isRunning()
    finally:
        release_dial.set()
        qtbot.waitUntil(lambda: not window._dial_thread.isRunning(), timeout=2000)
    qtbot.wait(50)

    assert window.close() is True


def test_single_click_on_all_calls_row_no_longer_navigates(qtbot, connection):
    contacts = ContactRepository(connection)
    contact_id = contacts.upsert("+491234567")
    CallRepository(connection).insert(
        contact_id=contact_id,
        call_type=1,
        caller_number="+491234567",
        called_number=None,
        port="1",
        device="Fritz!Fon",
        call_date="2026-06-01T10:00:00",
        duration_seconds=30,
        raw_name=None,
    )

    window = MainWindow(connection)
    qtbot.addWidget(window)
    window._all_calls_view.reload()
    window._tabs.setCurrentIndex(0)  # Alle Anrufe

    window._all_calls_view._table.clicked.emit(window._all_calls_view._model.index(0, 2))

    assert window._tabs.currentIndex() == 0  # kein Tabwechsel durch Einfachklick


def test_datei_menu_has_settings_action(qtbot, connection):
    window = MainWindow(connection)
    qtbot.addWidget(window)

    # .menu() muss ausserhalb des Generators gebunden werden - sonst hat sich
    # der zurückgegebene QMenu-Wrapper in der Praxis als vorzeitig von
    # shiboken zerstört erwiesen (RuntimeError "Internal C++ object already
    # deleted"), obwohl dieselbe Instanz über self._file_menu am Leben bleibt.
    file_action = next(a for a in window.menuBar().actions() if a.text() == "Datei")
    file_menu = file_action.menu()
    assert any(action.text() == "Einstellungen…" for action in file_menu.actions())


def test_open_settings_dialog_saves_config_and_shows_restart_notice(qtbot, connection, mocker):
    mock_exec = mocker.patch(
        "fritz_callhistory.gui.main_window.SettingsDialog.exec",
        return_value=QDialog.DialogCode.Accepted,
    )
    new_config = Config(sync_interval_minutes=99)
    mocker.patch("fritz_callhistory.gui.main_window.SettingsDialog.save", return_value=new_config)
    mock_information = mocker.patch("fritz_callhistory.gui.main_window.QMessageBox.information")

    window = MainWindow(connection, list_phonebooks_fn=None)
    qtbot.addWidget(window)

    window._open_settings_dialog()

    mock_exec.assert_called_once()
    mock_information.assert_called_once()
    assert window._config is new_config


def test_open_settings_dialog_without_list_phonebooks_fn_marks_unavailable(qtbot, connection, mocker):
    mocker.patch(
        "fritz_callhistory.gui.main_window.SettingsDialog.exec",
        return_value=QDialog.DialogCode.Rejected,
    )
    mock_set_unavailable = mocker.patch(
        "fritz_callhistory.gui.main_window.SettingsDialog.set_phonebooks_unavailable"
    )
    mock_worker_cls = mocker.patch("fritz_callhistory.gui.main_window.PhonebookListWorker")

    window = MainWindow(connection, list_phonebooks_fn=None)
    qtbot.addWidget(window)

    window._open_settings_dialog()

    mock_set_unavailable.assert_called_once()
    mock_worker_cls.assert_not_called()


def test_open_settings_dialog_starts_phonebook_list_worker_when_available(qtbot, connection, mocker):
    mocker.patch(
        "fritz_callhistory.gui.main_window.SettingsDialog.exec",
        return_value=QDialog.DialogCode.Rejected,
    )
    mock_worker_cls = mocker.patch("fritz_callhistory.gui.main_window.PhonebookListWorker")
    mock_worker = mock_worker_cls.return_value

    list_phonebooks_fn = mocker.Mock(return_value=[(0, "Telefonbuch")])
    window = MainWindow(connection, list_phonebooks_fn=list_phonebooks_fn)
    qtbot.addWidget(window)

    window._open_settings_dialog()

    mock_worker_cls.assert_called_once_with(list_phonebooks_fn, parent=window)
    mock_worker.start.assert_called_once()
