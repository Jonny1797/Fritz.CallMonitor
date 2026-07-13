from fritz_callhistory.db.repository import CallRepository, ContactRepository
from fritz_callhistory.gui.calls_tab import CallsTab


def _insert_call(calls, *, contact_id, call_date="2026-06-01T10:00:00", call_type=1):
    calls.insert(
        contact_id=contact_id,
        call_type=call_type,
        caller_number="+491234567",
        called_number=None,
        port="1",
        device="Fritz!Fon",
        call_date=call_date,
        duration_seconds=30,
        raw_name=None,
    )


def test_starts_ungrouped_showing_all_calls_view(qtbot, connection):
    tab = CallsTab(connection)
    qtbot.addWidget(tab)

    assert tab._stack.currentWidget() is tab.all_calls_view
    assert not tab._grouped


def test_toggling_gruppieren_switches_to_contacts_view_and_reloads(qtbot, connection):
    tab = CallsTab(connection)
    qtbot.addWidget(tab)
    ContactRepository(connection).upsert("+491234567")
    assert tab.contacts_view._contact_model.rowCount() == 0

    tab._set_grouped(True)

    assert tab._stack.currentWidget() is tab.contacts_view
    assert tab.contacts_view._contact_model.rowCount() == 1
    assert tab._group_toggle.text() == "Gruppierung aufheben"


def test_untoggling_gruppieren_shows_all_calls_view_again(qtbot, connection):
    tab = CallsTab(connection)
    qtbot.addWidget(tab)

    tab._set_grouped(True)
    tab._set_grouped(False)

    assert tab._stack.currentWidget() is tab.all_calls_view
    assert tab._group_toggle.text() == "Gruppieren"


def test_selecting_from_all_calls_switches_to_grouped_mode_and_selects_contact(qtbot, connection):
    contacts = ContactRepository(connection)
    id_a = contacts.upsert("+491111111")
    contacts.set_display_name(id_a, "Bertha")
    contacts.upsert("+492222222")

    tab = CallsTab(connection)
    qtbot.addWidget(tab)
    tab.contacts_view._table.horizontalHeader().sectionClicked.emit(0)  # Name aufsteigend

    tab.all_calls_view.contact_selected.emit(id_a)

    assert tab._grouped
    assert "Bertha" in tab.contacts_view._detail._title_label.text()


def test_double_clicking_all_calls_row_switches_to_grouped_mode(qtbot, connection):
    contacts = ContactRepository(connection)
    contact_id = contacts.upsert("+491234567")
    contacts.set_display_name(contact_id, "Max Mustermann")
    _insert_call(CallRepository(connection), contact_id=contact_id)

    tab = CallsTab(connection)
    qtbot.addWidget(tab)
    tab.all_calls_view.reload()

    tab.all_calls_view._table.doubleClicked.emit(tab.all_calls_view._model.index(0, 2))

    assert tab._grouped
    assert "Max Mustermann" in tab.contacts_view._detail._title_label.text()


def test_single_click_on_all_calls_row_does_not_switch_mode(qtbot, connection):
    contacts = ContactRepository(connection)
    contact_id = contacts.upsert("+491234567")
    _insert_call(CallRepository(connection), contact_id=contact_id)

    tab = CallsTab(connection)
    qtbot.addWidget(tab)
    tab.all_calls_view.reload()

    tab.all_calls_view._table.clicked.emit(tab.all_calls_view._model.index(0, 2))

    assert not tab._grouped


def test_show_contact_switches_to_grouped_mode(qtbot, connection):
    contacts = ContactRepository(connection)
    contact_id = contacts.upsert("+491234567")
    contacts.set_display_name(contact_id, "Max Mustermann")

    tab = CallsTab(connection)
    qtbot.addWidget(tab)

    tab.show_contact(contact_id)

    assert tab._grouped
    assert "Max Mustermann" in tab.contacts_view._detail._title_label.text()


def test_call_requested_forwarded_from_both_children(qtbot, connection):
    tab = CallsTab(connection)
    qtbot.addWidget(tab)
    received = []
    tab.call_requested.connect(received.append)

    tab.all_calls_view.call_requested.emit("+491111111")
    tab.contacts_view.call_requested.emit("+492222222")

    assert received == ["+491111111", "+492222222"]


def test_number_double_clicked_forwarded_from_contacts_view(qtbot, connection):
    tab = CallsTab(connection)
    qtbot.addWidget(tab)
    received = []
    tab.number_double_clicked.connect(received.append)

    tab.contacts_view.number_double_clicked.emit("+491234567")

    assert received == ["+491234567"]


def test_typing_search_in_all_calls_view_mirrors_to_contacts_view(qtbot, connection):
    tab = CallsTab(connection)
    qtbot.addWidget(tab)

    tab.all_calls_view._search_edit.setText("Bertha")

    assert tab.contacts_view._search_edit.text() == "Bertha"


def test_typing_search_in_contacts_view_mirrors_to_all_calls_view(qtbot, connection):
    tab = CallsTab(connection)
    qtbot.addWidget(tab)

    tab.contacts_view._search_edit.setText("+4922")

    assert tab.all_calls_view._search_edit.text() == "+4922"


def test_mirrored_search_is_applied_when_switching_to_grouped_view(qtbot, connection):
    contacts = ContactRepository(connection)
    id_a = contacts.upsert("+491111111")
    contacts.set_display_name(id_a, "Bertha")
    contacts.upsert("+492222222")

    tab = CallsTab(connection)
    qtbot.addWidget(tab)

    tab.all_calls_view._search_edit.setText("Bertha")
    tab._set_grouped(True)

    assert tab.contacts_view._contact_model.rowCount() == 1
    assert tab.contacts_view._contact_model.contact_at(0).id == id_a


def test_mirrored_search_is_applied_when_switching_to_flat_view(qtbot, connection):
    contacts = ContactRepository(connection)
    contact_id = contacts.upsert("+491234567")
    contacts.set_display_name(contact_id, "Max Mustermann")
    other_id = contacts.upsert("+499999999")
    _insert_call(CallRepository(connection), contact_id=contact_id)
    _insert_call(CallRepository(connection), contact_id=other_id)

    tab = CallsTab(connection)
    qtbot.addWidget(tab)
    tab._set_grouped(True)

    tab.contacts_view._search_edit.setText("Max")
    tab._set_grouped(False)

    assert tab.all_calls_view._model.rowCount() == 1


def test_double_clicking_all_calls_row_clears_mirrored_search_in_both_views(qtbot, connection):
    contacts = ContactRepository(connection)
    contact_id = contacts.upsert("+491234567")
    contacts.set_display_name(contact_id, "Max Mustermann")
    _insert_call(CallRepository(connection), contact_id=contact_id)

    tab = CallsTab(connection)
    qtbot.addWidget(tab)
    tab.all_calls_view.reload()
    tab.all_calls_view._search_edit.setText("Max")

    tab.all_calls_view._table.doubleClicked.emit(tab.all_calls_view._model.index(0, 2))

    assert tab.contacts_view._search_edit.text() == ""
    assert tab.all_calls_view._search_edit.text() == ""


def test_focus_search_delegates_to_currently_visible_page(qtbot, connection):
    tab = CallsTab(connection)
    qtbot.addWidget(tab)
    tab.show()
    qtbot.waitExposed(tab)
    tab.activateWindow()
    tab.raise_()

    # Fenster-Aktivierung läuft auf der offscreen-QPA-Plattform asynchron -
    # waitUntil() statt einer festen Wartezeit, da die Latenz unter Last
    # (z.B. voller Testsuite) schwankt.
    tab.focus_search()
    qtbot.waitUntil(tab.all_calls_view._search_edit.hasFocus, timeout=2000)

    tab._set_grouped(True)
    tab.focus_search()
    qtbot.waitUntil(tab.contacts_view._search_edit.hasFocus, timeout=2000)


def test_dial_selected_delegates_to_currently_visible_page(qtbot, connection):
    contacts = ContactRepository(connection)
    contact_id = contacts.upsert("+491234567")
    _insert_call(CallRepository(connection), contact_id=contact_id)

    tab = CallsTab(connection)
    qtbot.addWidget(tab)
    tab.all_calls_view.reload()
    tab.all_calls_view._table.selectRow(0)
    received = []
    tab.call_requested.connect(received.append)

    tab.dial_selected()

    assert received == ["+491234567"]


def test_search_does_not_bounce_back_and_forth_between_views(qtbot, connection):
    tab = CallsTab(connection)
    qtbot.addWidget(tab)
    all_calls_changes = []
    contacts_changes = []
    tab.all_calls_view.search_changed.connect(all_calls_changes.append)
    tab.contacts_view.search_changed.connect(contacts_changes.append)

    tab.all_calls_view._search_edit.setText("Bertha")

    assert all_calls_changes == ["Bertha"]
    assert contacts_changes == []
