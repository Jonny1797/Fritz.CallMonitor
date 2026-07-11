from fritz_callhistory.db.repository import CallRepository, ContactRepository
from fritz_callhistory.gui.contacts_view import GroupedContactsView


def test_table_and_call_table_are_direct_splitter_children(qtbot, connection):
    # Beide Tabellen sind der alleinige Inhalt ihres jeweiligen Splitter-Kinds
    # (kein interner Header mehr, der eine Tabelle kürzer macht als die
    # andere) - der Splitter gibt beiden Kindern dieselbe Gesamthöhe, also
    # enden beide Tabellen automatisch gleich hoch.
    view = GroupedContactsView(connection)
    qtbot.addWidget(view)

    assert view._table.parentWidget() is view._detail.parentWidget()


def test_contact_detail_labels_shown_in_full_width_header_above_splitter(qtbot, connection):
    contacts = ContactRepository(connection)
    contact_id = contacts.upsert("+491234567")
    contacts.set_display_name(contact_id, "Max Mustermann")

    view = GroupedContactsView(connection)
    qtbot.addWidget(view)
    view._table.selectRow(0)

    assert "Max Mustermann" in view._detail.title_label.text()
    # Kein Splitter-Kind mehr - liegt jetzt oberhalb, als Geschwister des Splitters.
    assert view._detail.title_label.parentWidget() is not view._detail


def test_contact_table_sorting_cycles_and_selection_still_resolves(qtbot, connection):
    contacts = ContactRepository(connection)
    id_a = contacts.upsert("+491111111")
    contacts.set_display_name(id_a, "Bertha")
    id_b = contacts.upsert("+492222222")
    contacts.set_display_name(id_b, "Anton")

    view = GroupedContactsView(connection)
    qtbot.addWidget(view)
    header = view._table.horizontalHeader()

    header.sectionClicked.emit(0)  # Name aufsteigend
    assert view._contact_proxy.data(view._contact_proxy.index(0, 0)) == "Anton"

    view._table.selectRow(0)
    assert "Anton" in view._detail._title_label.text()

    header.sectionClicked.emit(0)  # absteigend
    header.sectionClicked.emit(0)  # zurück zur Ausgangsreihenfolge

    assert view._contact_proxy.data(view._contact_proxy.index(0, 0)) == "Bertha"


def test_shows_seeded_contacts(qtbot, connection):
    contacts = ContactRepository(connection)
    contacts.upsert("+491234567")
    contact_id = contacts.upsert("+499876543")
    contacts.set_display_name(contact_id, "Max Mustermann")

    view = GroupedContactsView(connection)
    qtbot.addWidget(view)

    model = view._contact_model
    assert model.rowCount() == 2
    numbers = {model.contact_at(row).primary_number for row in range(model.rowCount())}
    assert numbers == {"+491234567", "+499876543"}


def test_reload_contacts_picks_up_new_contacts(qtbot, connection):
    view = GroupedContactsView(connection)
    qtbot.addWidget(view)
    assert view._contact_model.rowCount() == 0

    ContactRepository(connection).upsert("+491234567")
    view.reload_contacts()

    assert view._contact_model.rowCount() == 1


def test_search_filters_by_name_and_number(qtbot, connection):
    contacts = ContactRepository(connection)
    contact_id = contacts.upsert("+491234567")
    contacts.set_display_name(contact_id, "Max Mustermann")
    contacts.upsert("+499876543")

    view = GroupedContactsView(connection)
    qtbot.addWidget(view)
    assert view._contact_model.rowCount() == 2

    view._search_edit.setText("Mustermann")
    qtbot.wait(400)

    assert view._contact_model.rowCount() == 1
    assert view._contact_model.contact_at(0).primary_number == "+491234567"


def test_search_by_number_fragment(qtbot, connection):
    contacts = ContactRepository(connection)
    contacts.upsert("+491234567")
    contacts.upsert("+499876543")

    view = GroupedContactsView(connection)
    qtbot.addWidget(view)

    view._search_edit.setText("9876543")
    qtbot.wait(400)

    assert view._contact_model.rowCount() == 1
    assert view._contact_model.contact_at(0).primary_number == "+499876543"


def test_clearing_search_shows_all_contacts_again(qtbot, connection):
    contacts = ContactRepository(connection)
    contacts.upsert("+491234567")
    contacts.upsert("+499876543")

    view = GroupedContactsView(connection)
    qtbot.addWidget(view)

    view._search_edit.setText("1234567")
    qtbot.wait(400)
    assert view._contact_model.rowCount() == 1

    view._search_edit.setText("")
    qtbot.wait(400)
    assert view._contact_model.rowCount() == 2


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

    view = GroupedContactsView(connection)
    qtbot.addWidget(view)

    view._table.selectRow(0)

    assert "Max Mustermann" in view._detail._title_label.text()
    assert view._detail._call_model.rowCount() == 1


def test_search_reset_clears_detail_view(qtbot, connection):
    contacts = ContactRepository(connection)
    contact_id = contacts.upsert("+491234567")
    contacts.set_display_name(contact_id, "Max Mustermann")

    view = GroupedContactsView(connection)
    qtbot.addWidget(view)
    view._table.selectRow(0)
    assert "Max Mustermann" in view._detail._title_label.text()

    view._search_edit.setText("kein-treffer-xyz")
    qtbot.wait(400)

    assert view._detail._title_label.text() == "Wählen Sie einen Kontakt aus, um mehr Details zu sehen."


def test_double_clicking_contact_name_column_emits_number_double_clicked(qtbot, connection):
    contacts = ContactRepository(connection)
    contacts.upsert("+491234567")

    view = GroupedContactsView(connection)
    qtbot.addWidget(view)

    with qtbot.waitSignal(view.number_double_clicked, timeout=1000) as blocker:
        view._on_contact_table_double_clicked(view._contact_model.index(0, 0))

    assert blocker.args == ["+491234567"]


def test_double_clicking_contact_other_columns_does_nothing(qtbot, connection):
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

    view = GroupedContactsView(connection)
    qtbot.addWidget(view)
    received = []
    view.number_double_clicked.connect(received.append)

    view._on_contact_table_double_clicked(view._contact_model.index(0, 1))
    view._on_contact_table_double_clicked(view._contact_model.index(0, 2))

    assert received == []


def test_double_clicking_call_detail_number_emits_number_double_clicked(qtbot, connection):
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

    view = GroupedContactsView(connection)
    qtbot.addWidget(view)
    view._table.selectRow(0)

    with qtbot.waitSignal(view.number_double_clicked, timeout=1000) as blocker:
        view._detail._call_table.doubleClicked.emit(view._detail._call_model.index(0, 2))

    assert blocker.args == ["+491234567"]


def test_contact_number_for_row_returns_primary_number(qtbot, connection):
    contacts = ContactRepository(connection)
    contacts.upsert("+491234567")

    view = GroupedContactsView(connection)
    qtbot.addWidget(view)

    assert view._contact_number_for_row(0) == "+491234567"


def test_contact_number_for_row_returns_none_for_anonymous_contact(qtbot, connection):
    contacts = ContactRepository(connection)
    contacts.upsert("anonymous", is_anonymous=True)

    view = GroupedContactsView(connection)
    qtbot.addWidget(view)

    assert view._contact_number_for_row(0) is None


def test_show_contact_selects_row(qtbot, connection):
    contacts = ContactRepository(connection)
    id_a = contacts.upsert("+491111111")
    contacts.set_display_name(id_a, "Bertha")
    id_b = contacts.upsert("+492222222")
    contacts.set_display_name(id_b, "Anton")

    view = GroupedContactsView(connection)
    qtbot.addWidget(view)
    view._table.horizontalHeader().sectionClicked.emit(0)  # Name aufsteigend

    view.show_contact(id_a)

    assert "Bertha" in view._detail._title_label.text()


def test_show_contact_clears_active_search_filter(qtbot, connection):
    contacts = ContactRepository(connection)
    contact_id = contacts.upsert("+491234567")
    contacts.set_display_name(contact_id, "Max Mustermann")

    view = GroupedContactsView(connection)
    qtbot.addWidget(view)
    view._search_edit.setText("passt-nicht-zu-max")
    view._search_timer.timeout.emit()
    assert view._contact_model.rowCount() == 0

    view.show_contact(contact_id)

    assert view._search_edit.text() == ""
    assert view._contact_model.rowCount() == 1
    assert "Max Mustermann" in view._detail._title_label.text()
