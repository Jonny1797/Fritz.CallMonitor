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
    assert "Kontakt aus" not in widget._title_label.text()

    widget.clear()

    assert widget._title_label.text() == "Wählen Sie einen Kontakt aus, um mehr Details zu sehen."
    assert widget._call_model.rowCount() == 0


def test_call_table_sorting_cycles_asc_desc_unsorted(qtbot, connection):
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_id = contacts.upsert("+491234567")

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
    header = widget._call_table.horizontalHeader()

    header.sectionClicked.emit(0)  # aufsteigend
    assert widget._call_proxy.data(widget._call_proxy.index(0, 0)) == "01.06.2026, 10:00"

    header.sectionClicked.emit(0)  # absteigend
    assert widget._call_proxy.data(widget._call_proxy.index(0, 0)) == "03.06.2026, 10:00"

    header.sectionClicked.emit(0)  # zurueck zur Ausgangsreihenfolge (neueste zuerst)
    assert widget._call_proxy.data(widget._call_proxy.index(0, 0)) == "03.06.2026, 10:00"


def test_double_click_number_resolves_correct_row_while_sorted(qtbot, connection):
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_id = contacts.upsert("+491234567")
    calls.insert(
        contact_id=contact_id,
        call_type=1,
        caller_number="+491111111",
        called_number=None,
        port="1",
        device="Fritz!Fon",
        call_date="2026-06-01T10:00:00",
        duration_seconds=30,
        raw_name=None,
    )
    calls.insert(
        contact_id=contact_id,
        call_type=1,
        caller_number="+492222222",
        called_number=None,
        port="1",
        device="Fritz!Fon",
        call_date="2026-06-03T10:00:00",
        duration_seconds=30,
        raw_name=None,
    )

    widget = ContactDetailWidget(connection)
    qtbot.addWidget(widget)
    widget.show_contact(contacts.get(contact_id))
    widget._call_table.horizontalHeader().sectionClicked.emit(0)  # aufsteigend -> aeltester zuerst
    signal_spy = []
    widget.number_double_clicked.connect(signal_spy.append)

    widget._call_table.doubleClicked.emit(widget._call_proxy.index(0, 2))

    assert signal_spy == ["+491111111"]
