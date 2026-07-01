from fritz_callhistory.db.repository import CallRepository, ContactRepository
from fritz_callhistory.gui.contact_detail import ContactDetailWidget


def test_show_contact_lists_calls_newest_first(qtbot, connection):
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_id = contacts.upsert("+491234567")
    contacts.set_display_name(contact_id, "Max Mustermann")

    for date in ["2026-06-01T10:00:00", "2026-06-03T10:00:00"]:
        calls.insert(
            contact_id=contact_id,
            call_type=1,
            caller_number="+491234567",
            called_number=None,
            port="1",
            device="Fritz!Fon",
            call_date=date,
            duration_seconds=30,
            raw_name=None,
        )

    widget = ContactDetailWidget(connection)
    qtbot.addWidget(widget)

    widget.show_contact(contacts.get(contact_id))

    assert widget._call_model.rowCount() == 2
    assert "Max Mustermann" in widget._title_label.text()
    assert "+491234567" in widget._subtitle_label.text()


def test_clear_resets_widget(qtbot, connection):
    contacts = ContactRepository(connection)
    contact_id = contacts.upsert("+491234567")

    widget = ContactDetailWidget(connection)
    qtbot.addWidget(widget)
    widget.show_contact(contacts.get(contact_id))
    assert widget._title_label.text() != "Kein Kontakt ausgewählt"

    widget.clear()

    assert widget._title_label.text() == "Kein Kontakt ausgewählt"
    assert widget._call_model.rowCount() == 0
