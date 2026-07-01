from fritz_callhistory.db.repository import CallRepository, ContactRepository
from fritz_callhistory.fritz.exceptions import FritzBoxConnectionError
from fritz_callhistory.gui.main_window import MainWindow


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

    assert window._detail._title_label.text() == "Kein Kontakt ausgewählt"


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


def test_sync_button_shows_error_on_failure(qtbot, connection):
    def failing_sync():
        raise FritzBoxConnectionError("Box nicht erreichbar")

    window = MainWindow(connection, sync_fn=failing_sync)
    qtbot.addWidget(window)

    window._sync_button.click()
    qtbot.waitUntil(lambda: "fehlgeschlagen" in window.statusBar().currentMessage(), timeout=3000)

    assert "Box nicht erreichbar" in window.statusBar().currentMessage()
    assert window._sync_button.isEnabled()
