from fritz_callhistory.db.repository import CallRepository, ContactRepository, SyncStateRepository
from fritz_callhistory.fritz.exceptions import FritzBoxConnectionError
from fritz_callhistory.gui.all_calls_view import _LAST_SEEN_KEY
from fritz_callhistory.gui.main_window import MainWindow


def test_contact_table_and_call_table_are_direct_splitter_children(qtbot, connection):
    # Beide Tabellen sind der alleinige Inhalt ihres jeweiligen Splitter-Kinds
    # (kein interner Header mehr, der eine Tabelle kuerzer macht als die
    # andere) - der Splitter gibt beiden Kindern dieselbe Gesamthoehe, also
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
    header.sectionClicked.emit(0)  # zurueck zur Ausgangsreihenfolge

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


def test_call_monitor_connection_lost_message_shown_only_once(qtbot, connection):
    window = MainWindow(connection)
    qtbot.addWidget(window)

    window._on_call_monitor_connection_lost("Connection refused")
    assert "#96*5*" in window.statusBar().currentMessage()

    window.statusBar().clearMessage()
    window._on_call_monitor_connection_lost("Connection refused again")
    assert window.statusBar().currentMessage() == ""


def test_main_window_has_three_tabs(qtbot, connection):
    window = MainWindow(connection)
    qtbot.addWidget(window)

    assert window._tabs.count() == 3
    assert window._tabs.tabText(0) == "Kontakte"
    assert window._tabs.tabText(1) == "Alle Anrufe"
    assert window._tabs.tabText(2) == "Telefonbuch"


def test_existing_widgets_still_reachable_after_tab_refactor(qtbot, connection):
    contacts = ContactRepository(connection)
    contacts.upsert("+491234567")

    window = MainWindow(connection)
    qtbot.addWidget(window)

    assert window._contact_model.rowCount() == 1
    window._search_edit.setText("kein-treffer")
    window._search_timer.timeout.emit()
    assert window._contact_model.rowCount() == 0
    assert window._sync_button.isEnabled() is False  # kein sync_fn uebergeben


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

    assert window._tabs.currentIndex() == 0
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

    assert window._tabs.tabText(1) == "Alle Anrufe (1 neu verpasst)"


def test_all_calls_tab_label_stays_plain_when_no_new_missed_calls(qtbot, connection):
    window = MainWindow(connection)
    qtbot.addWidget(window)

    assert window._tabs.tabText(1) == "Alle Anrufe"


def test_all_calls_tab_label_updates_after_manual_reload(qtbot, connection):
    SyncStateRepository(connection).set(_LAST_SEEN_KEY, "2026-06-01T00:00:00")
    window = MainWindow(connection)
    qtbot.addWidget(window)
    assert window._tabs.tabText(1) == "Alle Anrufe"

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

    assert window._tabs.tabText(1) == "Alle Anrufe (1 neu verpasst)"


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
    mock_thread.connected.connect.assert_called_once_with(window._all_calls_view.on_live_connected)
    mock_thread.disconnected.connect.assert_called_once_with(
        window._all_calls_view.on_live_disconnected
    )
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

    assert window._tabs.currentIndex() == 0
    assert "Max Mustermann" in window._detail._title_label.text()


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
    window._tabs.setCurrentIndex(1)  # Alle Anrufe

    window._all_calls_view._table.clicked.emit(window._all_calls_view._model.index(0, 2))

    assert window._tabs.currentIndex() == 1  # kein Tabwechsel durch Einfachklick
