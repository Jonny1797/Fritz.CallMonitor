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
    assert "+49 1234567" in widget._subtitle_label.text()


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

    header.sectionClicked.emit(0)  # zurück zur Ausgangsreihenfolge (neueste zuerst)
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
    widget._call_table.horizontalHeader().sectionClicked.emit(0)  # aufsteigend -> ältester zuerst
    signal_spy = []
    widget.number_double_clicked.connect(signal_spy.append)

    widget._call_table.doubleClicked.emit(widget._call_proxy.index(0, 2))

    assert signal_spy == ["+491111111"]


def test_number_for_row_returns_call_number(qtbot, connection):
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_id = contacts.upsert("+491234567")
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

    widget = ContactDetailWidget(connection)
    qtbot.addWidget(widget)
    widget.show_contact(contacts.get(contact_id))

    assert widget._number_for_row(0) == "+491234567"


def test_number_for_row_returns_none_for_anonymous_number(qtbot, connection):
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_id = contacts.upsert("anonymous", is_anonymous=True)
    calls.insert(
        contact_id=contact_id,
        call_type=2,
        caller_number=None,
        called_number=None,
        port="1",
        device="Fritz!Fon",
        call_date="2026-06-01T10:00:00",
        duration_seconds=None,
        raw_name=None,
    )

    widget = ContactDetailWidget(connection)
    qtbot.addWidget(widget)
    widget.show_contact(contacts.get(contact_id))

    assert widget._number_for_row(0) is None


class _FakeSignal:
    def __init__(self):
        self.callback = None

    def connect(self, callback):
        self.callback = callback


class _FakeAction:
    def __init__(self):
        self.triggered = _FakeSignal()


class _FakeMenu:
    """Siehe tests/test_models.py für die Begründung: echtes QMenu.exec()
    lässt sich in PySide6 nicht per einfachem Attribut-Patch abfangen."""

    def __init__(self, parent=None):
        self._action: _FakeAction | None = None

    def addAction(self, text):
        self._action = _FakeAction()
        return self._action

    def exec(self, pos):
        if self._action is not None and self._action.triggered.callback is not None:
            self._action.triggered.callback()


def test_right_click_call_table_emits_call_requested(qtbot, connection, mocker):
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_id = contacts.upsert("+491234567")
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

    widget = ContactDetailWidget(connection)
    qtbot.addWidget(widget)
    widget.resize(400, 200)
    widget.show()
    widget.show_contact(contacts.get(contact_id))
    mocker.patch("fritz_callhistory.gui.models.QMenu", side_effect=_FakeMenu)
    signal_spy = []
    widget.call_requested.connect(signal_spy.append)

    rect = widget._call_table.visualRect(widget._call_proxy.index(0, 2))
    widget._call_table.customContextMenuRequested.emit(rect.center())

    assert signal_spy == ["+491234567"]
