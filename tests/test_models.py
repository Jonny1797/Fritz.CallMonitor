import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableView

from fritz_callhistory.db.repository import (
    CallRecord,
    CallWithContact,
    Contact,
    LocalPhonebookContact,
    PhonebookNumber,
    VoicemailMessageRecord,
)
from fritz_callhistory.gui.models import (
    AllCallsListModel,
    CallListModel,
    ContactListModel,
    DataclassSortProxy,
    PhonebookContactListModel,
    VoicemailListModel,
    _format_call_date,
    install_call_context_menu,
    install_phonebook_call_context_menu,
    install_tristate_sorting,
    install_voicemail_context_menu,
    port_device_display,
)


def _voicemail_message(**overrides) -> VoicemailMessageRecord:
    defaults = dict(
        id=1,
        tam_index=0,
        box_path="/download.lua?path=/data/tam/rec/rec.0.000",
        caller_number="+491712345678",
        called_number="+4969123456",
        message_date="2026-06-01T10:00:00",
        duration_seconds=4,
        raw_name=None,
        is_new=True,
        is_hidden=False,
    )
    defaults.update(overrides)
    return VoicemailMessageRecord(**defaults)


def _call_record(call_type: int) -> CallRecord:
    return CallRecord(
        id=1,
        contact_id=1,
        call_type=call_type,
        caller_number="+491234567",
        called_number=None,
        port="1",
        device="Fritz!Fon",
        call_date="2026-06-01T10:00:00",
        duration_seconds=30,
        raw_name=None,
    )


def _call_with_contact(call_type: int, call_date: str = "2026-06-01T10:00:00") -> CallWithContact:
    return CallWithContact(
        id=1,
        contact_id=1,
        call_type=call_type,
        caller_number="+491234567",
        called_number=None,
        port="1",
        device="Fritz!Fon",
        call_date=call_date,
        duration_seconds=30,
        raw_name=None,
        contact_display_name="Max Mustermann",
        contact_primary_number="+491234567",
        contact_is_anonymous=False,
    )


@pytest.mark.parametrize(
    "call_type,expected_icon,expected_label",
    [
        (1, "↘", "Eingehend"),
        (2, "✕", "Verpasst"),
        (3, "↗", "Ausgehend"),
        (9, "↘", "Eingehend (aktiv)"),
        (10, "⊘", "Abgelehnt"),
        (11, "↗", "Ausgehend (aktiv)"),
    ],
)
def test_call_list_model_direction_column_shows_icon_and_label(
    qtbot, call_type, expected_icon, expected_label
):
    model = CallListModel([_call_record(call_type)])
    text = model.data(model.index(0, 1))
    assert text == f"{expected_icon} {expected_label}"


@pytest.mark.parametrize(
    "call_type,expected_icon,expected_label",
    [
        (1, "↘", "Eingehend"),
        (2, "✕", "Verpasst"),
        (3, "↗", "Ausgehend"),
        (9, "↘", "Eingehend (aktiv)"),
        (10, "⊘", "Abgelehnt"),
        (11, "↗", "Ausgehend (aktiv)"),
    ],
)
def test_all_calls_list_model_direction_column_shows_icon_and_label(
    qtbot, call_type, expected_icon, expected_label
):
    model = AllCallsListModel([_call_with_contact(call_type)])
    text = model.data(model.index(0, 1))
    assert text == f"{expected_icon} {expected_label}"


def test_new_missed_row_is_bold_and_red(qtbot):
    call = _call_with_contact(call_type=2, call_date="2026-06-02T10:00:00")
    model = AllCallsListModel([call], last_seen_at="2026-06-01T00:00:00")

    index = model.index(0, 0)
    font = model.data(index, Qt.ItemDataRole.FontRole)
    color = model.data(index, Qt.ItemDataRole.ForegroundRole)

    assert font is not None and font.bold() is True
    assert color is not None


def test_old_missed_row_has_no_highlight(qtbot):
    call = _call_with_contact(call_type=2, call_date="2026-06-01T00:00:00")
    model = AllCallsListModel([call], last_seen_at="2026-06-02T00:00:00")

    index = model.index(0, 0)
    assert model.data(index, Qt.ItemDataRole.FontRole) is None
    assert model.data(index, Qt.ItemDataRole.ForegroundRole) is None


def test_new_non_missed_row_has_no_highlight(qtbot):
    call = _call_with_contact(call_type=1, call_date="2026-06-02T10:00:00")
    model = AllCallsListModel([call], last_seen_at="2026-06-01T00:00:00")

    index = model.index(0, 0)
    assert model.data(index, Qt.ItemDataRole.FontRole) is None
    assert model.data(index, Qt.ItemDataRole.ForegroundRole) is None


def test_set_last_seen_at_updates_highlighting(qtbot):
    call = _call_with_contact(call_type=2, call_date="2026-06-02T10:00:00")
    model = AllCallsListModel([call], last_seen_at="2026-06-01T00:00:00")
    index = model.index(0, 0)
    assert model.data(index, Qt.ItemDataRole.FontRole) is not None

    model.set_last_seen_at("2026-06-03T00:00:00")

    assert model.data(index, Qt.ItemDataRole.FontRole) is None


@pytest.mark.parametrize(
    "call_date,expected",
    [
        ("2026-06-01T10:00:00", "01.06.2026, 10:00"),
        ("2026-12-13T16:10:42", "13.12.2026, 16:10"),
    ],
)
def test_format_call_date_is_human_readable_without_seconds(call_date, expected):
    assert _format_call_date(call_date) == expected


def test_call_list_model_uses_human_readable_date(qtbot):
    call = _call_record(call_type=1)
    call.call_date = "2026-07-03T14:22:00"
    model = CallListModel([call])

    assert model.data(model.index(0, 0)) == "03.07.2026, 14:22"


def test_all_calls_list_model_uses_human_readable_date(qtbot):
    call = _call_with_contact(call_type=1, call_date="2026-07-03T14:22:00")
    model = AllCallsListModel([call])

    assert model.data(model.index(0, 0)) == "03.07.2026, 14:22"


def test_contact_list_model_letzter_kontakt_uses_human_readable_date(qtbot):
    contact = Contact(
        id=1,
        primary_number="+491234567",
        display_name="Max Mustermann",
        is_anonymous=False,
        last_call_date="2026-07-03T14:22:00",
        call_count=1,
    )
    model = ContactListModel([contact])

    assert model.data(model.index(0, 2)) == "03.07.2026, 14:22"


def test_contact_list_model_letzter_kontakt_falls_back_to_dash(qtbot):
    contact = Contact(
        id=1,
        primary_number="+491234567",
        display_name=None,
        is_anonymous=False,
        last_call_date=None,
        call_count=0,
    )
    model = ContactListModel([contact])

    assert model.data(model.index(0, 2)) == "-"


@pytest.mark.parametrize(
    "device,port,expected",
    [
        ("-1", "1", "1"),
        ("-1", None, "-"),
        (None, None, "-"),
        ("Fritz!Fon", "1", "Fritz!Fon / 1"),
        ("Fritz!Fon", None, "Fritz!Fon"),
    ],
)
def test_port_device_display_filters_placeholder(device, port, expected):
    assert port_device_display(device, port) == expected


def test_call_list_model_device_column_hides_placeholder(qtbot):
    call = _call_record(call_type=10)
    call.device = "-1"
    call.port = None
    model = CallListModel([call])

    assert model.data(model.index(0, 4)) == "-"


def test_all_calls_list_model_device_column_hides_placeholder(qtbot):
    call = _call_with_contact(call_type=10)
    call.device = "-1"
    call.port = None
    model = AllCallsListModel([call])

    assert model.data(model.index(0, 4)) == "-"


def _local_phonebook_contact() -> LocalPhonebookContact:
    return LocalPhonebookContact(
        id=1,
        display_name="Max Mustermann",
        notes="VIP",
        box_uniqueid=None,
        numbers=[
            PhonebookNumber(
                id=1,
                number_raw="+491234567",
                number_normalized="+491234567",
                number_type="mobile",
                is_default=False,
            ),
            PhonebookNumber(
                id=2,
                number_raw="030 123",
                number_normalized="+4930123",
                number_type="home",
                is_default=False,
            ),
        ],
    )


def test_phonebook_contact_list_model_columns(qtbot):
    model = PhonebookContactListModel([_local_phonebook_contact()])

    assert model.data(model.index(0, 0)) == "Max Mustermann"
    assert model.data(model.index(0, 1)) == "+491234567 (mobile), 030 123 (home)"
    assert model.data(model.index(0, 2)) == "VIP"


def test_phonebook_contact_list_model_empty_numbers_and_notes(qtbot):
    contact = LocalPhonebookContact(id=1, display_name="Nur Name", notes=None, box_uniqueid=None, numbers=[])
    model = PhonebookContactListModel([contact])

    assert model.data(model.index(0, 1)) == "-"
    assert model.data(model.index(0, 2)) == "-"


def test_dataclass_sort_proxy_sorts_duration_numerically_not_lexicographically(qtbot):
    # "2:30" > "10:05" lexikographisch, aber 150s < 605s - der Proxy muss nach
    # dem rohen duration_seconds-Feld sortieren, nicht nach dem "m:ss"-Anzeigetext.
    short_call = _call_record(call_type=1)
    short_call.duration_seconds = 150
    long_call = _call_record(call_type=1)
    long_call.duration_seconds = 605
    model = CallListModel([long_call, short_call])
    proxy = DataclassSortProxy(row_getter=model.call_at, key_fns={3: lambda c: c.duration_seconds})
    proxy.setSourceModel(model)

    proxy.sort(3, Qt.SortOrder.AscendingOrder)

    assert proxy.data(proxy.index(0, 3)) == "2:30"
    assert proxy.data(proxy.index(1, 3)) == "10:05"


def test_dataclass_sort_proxy_none_keys_sort_first(qtbot):
    with_duration = _call_record(call_type=1)
    with_duration.duration_seconds = 10
    without_duration = _call_record(call_type=2)
    without_duration.duration_seconds = None
    model = CallListModel([with_duration, without_duration])
    proxy = DataclassSortProxy(row_getter=model.call_at, key_fns={3: lambda c: c.duration_seconds})
    proxy.setSourceModel(model)

    proxy.sort(3, Qt.SortOrder.AscendingOrder)

    assert proxy.data(proxy.index(0, 3)) == "-"


def test_install_tristate_sorting_cycles_ascending_descending_unsorted(qtbot):
    first = _call_record(call_type=1)
    first.call_date = "2026-06-01T10:00:00"
    second = _call_record(call_type=1)
    second.call_date = "2026-06-02T10:00:00"
    model = CallListModel([first, second])
    proxy = DataclassSortProxy(row_getter=model.call_at, key_fns={0: lambda c: c.call_date})
    proxy.setSourceModel(model)
    table = QTableView()
    table.setModel(proxy)
    qtbot.addWidget(table)
    install_tristate_sorting(table, proxy)
    header = table.horizontalHeader()

    header.sectionClicked.emit(0)  # aufsteigend
    assert [proxy.data(proxy.index(r, 0)) for r in range(2)] == [
        "01.06.2026, 10:00",
        "02.06.2026, 10:00",
    ]

    header.sectionClicked.emit(0)  # absteigend
    assert [proxy.data(proxy.index(r, 0)) for r in range(2)] == [
        "02.06.2026, 10:00",
        "01.06.2026, 10:00",
    ]

    header.sectionClicked.emit(0)  # zurueck zur Ausgangsreihenfolge
    assert [proxy.data(proxy.index(r, 0)) for r in range(2)] == [
        "01.06.2026, 10:00",
        "02.06.2026, 10:00",
    ]
    assert header.isSortIndicatorShown() is False


class _FakeSignal:
    def __init__(self):
        self.callback = None

    def connect(self, callback):
        self.callback = callback


class _FakeAction:
    def __init__(self, text=""):
        self.text = text
        self.triggered = _FakeSignal()


class _FakeMenu:
    """Ersetzt QMenu in Tests: echtes QMenu.exec() oeffnet ein blockierendes
    Popup, das sich in PySide6 nicht per einfachem Attribut-Patch abfangen
    laesst (Shiboken-gewrappte Methoden ignorieren das) - dieser Fake ruft
    stattdessen direkt die per triggered.connect() hinterlegten Callbacks der
    top-level Actions auf (nicht rekursiv in Untermenues - Tests fuer
    Untermenue-Eintraege loesen den gewuenschten Callback selbst manuell aus,
    siehe install_phonebook_call_context_menu-Tests)."""

    def __init__(self, parent=None, text=""):
        self.text = text
        self.actions: list[_FakeAction] = []
        self.submenus: list["_FakeMenu"] = []

    def addAction(self, text):
        action = _FakeAction(text)
        self.actions.append(action)
        return action

    def addMenu(self, text):
        submenu = _FakeMenu(text=text)
        self.submenus.append(submenu)
        return submenu

    def exec(self, pos):
        for action in self.actions:
            if action.triggered.callback is not None:
                action.triggered.callback()


def _capture_fake_menus(mocker) -> list[_FakeMenu]:
    created: list[_FakeMenu] = []

    def factory(parent=None):
        menu = _FakeMenu()
        created.append(menu)
        return menu

    mocker.patch("fritz_callhistory.gui.models.QMenu", side_effect=factory)
    return created


def _table_with_one_row(qtbot) -> tuple[QTableView, DataclassSortProxy]:
    model = CallListModel([_call_record(call_type=1)])
    proxy = DataclassSortProxy(row_getter=model.call_at, key_fns={})
    proxy.setSourceModel(model)
    table = QTableView()
    table.setModel(proxy)
    qtbot.addWidget(table)
    table.resize(400, 200)
    table.show()
    return table, proxy


def test_install_call_context_menu_invokes_on_call_for_valid_number(qtbot, mocker):
    table, proxy = _table_with_one_row(qtbot)
    on_call = mocker.Mock()
    install_call_context_menu(table, proxy, lambda row: "+491234567", on_call)
    mocker.patch("fritz_callhistory.gui.models.QMenu", side_effect=_FakeMenu)

    rect = table.visualRect(proxy.index(0, 0))
    table.customContextMenuRequested.emit(rect.center())

    on_call.assert_called_once_with("+491234567")


def test_install_call_context_menu_shows_no_menu_when_number_missing(qtbot, mocker):
    table, proxy = _table_with_one_row(qtbot)
    on_call = mocker.Mock()
    install_call_context_menu(table, proxy, lambda row: None, on_call)
    fake_menu_cls = mocker.patch("fritz_callhistory.gui.models.QMenu", side_effect=_FakeMenu)

    rect = table.visualRect(proxy.index(0, 0))
    table.customContextMenuRequested.emit(rect.center())

    on_call.assert_not_called()
    fake_menu_cls.assert_not_called()


def _phonebook_table_with_contacts(
    qtbot, contacts: list[LocalPhonebookContact]
) -> tuple[QTableView, DataclassSortProxy]:
    model = PhonebookContactListModel(contacts)
    proxy = DataclassSortProxy(row_getter=model.contact_at, key_fns={})
    proxy.setSourceModel(model)
    table = QTableView()
    table.setModel(proxy)
    qtbot.addWidget(table)
    table.resize(400, 200)
    table.show()
    return table, proxy


def test_install_phonebook_call_context_menu_no_menu_for_zero_numbers(qtbot, mocker):
    contact = LocalPhonebookContact(
        id=1, display_name="Nur Name", notes=None, box_uniqueid=None, numbers=[]
    )
    table, proxy = _phonebook_table_with_contacts(qtbot, [contact])
    on_call = mocker.Mock()
    install_phonebook_call_context_menu(table, proxy, proxy.sourceModel().contact_at, on_call)
    fake_menu_cls = mocker.patch("fritz_callhistory.gui.models.QMenu", side_effect=_FakeMenu)

    rect = table.visualRect(proxy.index(0, 0))
    table.customContextMenuRequested.emit(rect.center())

    on_call.assert_not_called()
    fake_menu_cls.assert_not_called()


def test_install_phonebook_call_context_menu_single_number_dials_normalized_number(qtbot, mocker):
    contact = LocalPhonebookContact(
        id=1,
        display_name="Max Mustermann",
        notes=None,
        box_uniqueid=None,
        numbers=[
            PhonebookNumber(
                id=1,
                number_raw="0171 2345678",
                number_normalized="+491712345678",
                number_type="mobile",
                is_default=False,
            )
        ],
    )
    table, proxy = _phonebook_table_with_contacts(qtbot, [contact])
    on_call = mocker.Mock()
    install_phonebook_call_context_menu(table, proxy, proxy.sourceModel().contact_at, on_call)
    mocker.patch("fritz_callhistory.gui.models.QMenu", side_effect=_FakeMenu)

    rect = table.visualRect(proxy.index(0, 0))
    table.customContextMenuRequested.emit(rect.center())

    on_call.assert_called_once_with("+491712345678")


def test_install_phonebook_call_context_menu_multiple_no_default_builds_submenu_with_all_numbers(
    qtbot, mocker
):
    contact = LocalPhonebookContact(
        id=1,
        display_name="Max Mustermann",
        notes=None,
        box_uniqueid=None,
        numbers=[
            PhonebookNumber(
                id=1,
                number_raw="+491234567",
                number_normalized="+491234567",
                number_type="home",
                is_default=False,
            ),
            PhonebookNumber(
                id=2,
                number_raw="+499876543",
                number_normalized="+499876543",
                number_type="mobile",
                is_default=False,
            ),
        ],
    )
    table, proxy = _phonebook_table_with_contacts(qtbot, [contact])
    on_call = mocker.Mock()
    install_phonebook_call_context_menu(table, proxy, proxy.sourceModel().contact_at, on_call)
    created = _capture_fake_menus(mocker)

    rect = table.visualRect(proxy.index(0, 0))
    table.customContextMenuRequested.emit(rect.center())

    menu = created[0]
    assert menu.actions == []
    assert len(menu.submenus) == 1
    submenu = menu.submenus[0]
    assert [a.text for a in submenu.actions] == ["+491234567", "+499876543"]
    on_call.assert_not_called()

    submenu.actions[1].triggered.callback()
    on_call.assert_called_once_with("+499876543")


def test_install_phonebook_call_context_menu_multiple_with_default_shows_standard_and_submenu_entries(
    qtbot, mocker
):
    contact = LocalPhonebookContact(
        id=1,
        display_name="Max Mustermann",
        notes=None,
        box_uniqueid=None,
        numbers=[
            PhonebookNumber(
                id=1,
                number_raw="+491234567",
                number_normalized="+491234567",
                number_type="home",
                is_default=False,
            ),
            PhonebookNumber(
                id=2,
                number_raw="+499876543",
                number_normalized="+499876543",
                number_type="mobile",
                is_default=True,
            ),
        ],
    )
    table, proxy = _phonebook_table_with_contacts(qtbot, [contact])
    on_call = mocker.Mock()
    install_phonebook_call_context_menu(table, proxy, proxy.sourceModel().contact_at, on_call)
    created = _capture_fake_menus(mocker)

    rect = table.visualRect(proxy.index(0, 0))
    table.customContextMenuRequested.emit(rect.center())

    menu = created[0]
    assert [a.text for a in menu.actions] == ["Standardnummer anrufen: +499876543"]
    assert len(menu.submenus) == 1
    assert [a.text for a in menu.submenus[0].actions] == ["+491234567", "+499876543"]
    # exec() (bereits von on_context_menu selbst aufgerufen) loest die einzige
    # Top-Level-Action automatisch aus, siehe _FakeMenu.exec().
    on_call.assert_called_once_with("+499876543")


def test_install_phonebook_call_context_menu_submenu_action_dials_correct_number_not_last_bound(
    qtbot, mocker
):
    contact = LocalPhonebookContact(
        id=1,
        display_name="Max Mustermann",
        notes=None,
        box_uniqueid=None,
        numbers=[
            PhonebookNumber(
                id=1, number_raw="A", number_normalized="+491111111", number_type="home", is_default=False
            ),
            PhonebookNumber(
                id=2, number_raw="B", number_normalized="+492222222", number_type="home", is_default=False
            ),
            PhonebookNumber(
                id=3, number_raw="C", number_normalized="+493333333", number_type="home", is_default=False
            ),
        ],
    )
    table, proxy = _phonebook_table_with_contacts(qtbot, [contact])
    on_call = mocker.Mock()
    install_phonebook_call_context_menu(table, proxy, proxy.sourceModel().contact_at, on_call)
    created = _capture_fake_menus(mocker)

    rect = table.visualRect(proxy.index(0, 0))
    table.customContextMenuRequested.emit(rect.center())

    submenu = created[0].submenus[0]
    submenu.actions[0].triggered.callback()

    on_call.assert_called_once_with("+491111111")


def test_voicemail_new_message_row_is_bold_and_red(qtbot):
    model = VoicemailListModel([_voicemail_message(is_new=True)])
    index = model.index(0, 0)

    assert model.data(index, Qt.ItemDataRole.FontRole) is not None
    assert model.data(index, Qt.ItemDataRole.ForegroundRole) is not None


def test_voicemail_heard_message_row_has_no_special_styling(qtbot):
    model = VoicemailListModel([_voicemail_message(is_new=False)])
    index = model.index(0, 0)

    assert model.data(index, Qt.ItemDataRole.FontRole) is None
    assert model.data(index, Qt.ItemDataRole.ForegroundRole) is None


def test_voicemail_caller_column_prefers_name_over_number(qtbot):
    model = VoicemailListModel([_voicemail_message(raw_name="Georg", caller_number="+491712345678")])

    assert model.data(model.index(0, 1)) == "Georg"


def test_voicemail_caller_column_falls_back_to_number_without_name(qtbot):
    model = VoicemailListModel([_voicemail_message(raw_name=None, caller_number="+491712345678")])

    assert model.data(model.index(0, 1)) == "+491712345678"


def test_voicemail_caller_column_shows_placeholder_when_anonymous(qtbot):
    model = VoicemailListModel([_voicemail_message(raw_name=None, caller_number=None)])

    assert model.data(model.index(0, 1)) == "Anonym / unterdrückt"


def _voicemail_table_with_one_row(qtbot, message=None) -> tuple[QTableView, DataclassSortProxy]:
    model = VoicemailListModel([message or _voicemail_message()])
    proxy = DataclassSortProxy(row_getter=model.message_at, key_fns={})
    proxy.setSourceModel(model)
    table = QTableView()
    table.setModel(proxy)
    qtbot.addWidget(table)
    table.resize(400, 200)
    table.show()
    return table, proxy


def test_install_voicemail_context_menu_call_action_uses_caller_number(qtbot, mocker):
    table, proxy = _voicemail_table_with_one_row(qtbot)
    on_call = mocker.Mock()
    install_voicemail_context_menu(
        table, proxy, proxy.sourceModel().message_at, on_call, mocker.Mock(), mocker.Mock()
    )
    mocker.patch("fritz_callhistory.gui.models.QMenu", side_effect=_FakeMenu)

    rect = table.visualRect(proxy.index(0, 0))
    table.customContextMenuRequested.emit(rect.center())

    on_call.assert_called_once_with("+491712345678")


def test_install_voicemail_context_menu_hides_call_action_when_anonymous(qtbot, mocker):
    message = _voicemail_message(caller_number=None)
    table, proxy = _voicemail_table_with_one_row(qtbot, message)
    on_call = mocker.Mock()
    install_voicemail_context_menu(
        table, proxy, proxy.sourceModel().message_at, on_call, mocker.Mock(), mocker.Mock()
    )
    created = _capture_fake_menus(mocker)

    rect = table.visualRect(proxy.index(0, 0))
    table.customContextMenuRequested.emit(rect.center())

    assert not any(action.text.startswith("Anrufen") for action in created[0].actions)
    on_call.assert_not_called()


def test_install_voicemail_context_menu_play_action_invokes_callback(qtbot, mocker):
    message = _voicemail_message()
    table, proxy = _voicemail_table_with_one_row(qtbot, message)
    on_play = mocker.Mock()
    install_voicemail_context_menu(
        table, proxy, proxy.sourceModel().message_at, mocker.Mock(), on_play, mocker.Mock()
    )
    mocker.patch("fritz_callhistory.gui.models.QMenu", side_effect=_FakeMenu)

    rect = table.visualRect(proxy.index(0, 0))
    table.customContextMenuRequested.emit(rect.center())

    on_play.assert_called_once_with(message)


def test_install_voicemail_context_menu_hide_action_invokes_callback(qtbot, mocker):
    message = _voicemail_message()
    table, proxy = _voicemail_table_with_one_row(qtbot, message)
    on_hide = mocker.Mock()
    install_voicemail_context_menu(
        table, proxy, proxy.sourceModel().message_at, mocker.Mock(), mocker.Mock(), on_hide
    )
    mocker.patch("fritz_callhistory.gui.models.QMenu", side_effect=_FakeMenu)

    rect = table.visualRect(proxy.index(0, 0))
    table.customContextMenuRequested.emit(rect.center())

    on_hide.assert_called_once_with(message)
