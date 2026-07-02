from datetime import date, datetime

from PySide6.QtCore import Qt

from fritz_callhistory.db.repository import CallRepository, ContactRepository, SyncStateRepository
from fritz_callhistory.gui.all_calls_view import _LAST_SEEN_KEY, AllCallsView


def _insert_call(calls, *, contact_id, call_date, call_type=1):
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


def _fixed_today():
    return date(2026, 6, 15)


def _fixed_now():
    return datetime(2026, 6, 15, 12, 0, 0)


def test_view_lists_calls_across_contacts(qtbot, connection):
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_a = contacts.upsert("+491111111")
    contact_b = contacts.upsert("+492222222")
    _insert_call(calls, contact_id=contact_a, call_date="2026-06-01T10:00:00")
    _insert_call(calls, contact_id=contact_b, call_date="2026-06-02T10:00:00")

    view = AllCallsView(connection, today_provider=_fixed_today)
    qtbot.addWidget(view)

    assert view._model.rowCount() == 2


def test_name_number_column_shows_display_name_when_available(qtbot, connection):
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_id = contacts.upsert("+491234567")
    contacts.set_display_name(contact_id, "Max Mustermann")
    _insert_call(calls, contact_id=contact_id, call_date="2026-06-01T10:00:00")

    view = AllCallsView(connection, today_provider=_fixed_today)
    qtbot.addWidget(view)

    assert view._model.call_at(0).contact_display_name == "Max Mustermann"
    index = view._model.index(0, 2)
    assert view._model.data(index) == "Max Mustermann"


def test_name_number_column_falls_back_to_number_without_display_name(qtbot, connection):
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_id = contacts.upsert("+491234567")
    _insert_call(calls, contact_id=contact_id, call_date="2026-06-01T10:00:00")

    view = AllCallsView(connection, today_provider=_fixed_today)
    qtbot.addWidget(view)

    index = view._model.index(0, 2)
    assert view._model.data(index) == "+491234567"


def test_name_number_column_shows_anonymous_label(qtbot, connection):
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_id = contacts.upsert("anonymous", is_anonymous=True)
    _insert_call(calls, contact_id=contact_id, call_date="2026-06-01T10:00:00")

    view = AllCallsView(connection, today_provider=_fixed_today)
    qtbot.addWidget(view)

    index = view._model.index(0, 2)
    assert view._model.data(index) == "Anonym / unterdrückt"


def test_preset_today_filters_to_single_day(qtbot, connection):
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_id = contacts.upsert("+491234567")
    _insert_call(calls, contact_id=contact_id, call_date="2026-06-15T10:00:00")
    _insert_call(calls, contact_id=contact_id, call_date="2026-06-14T10:00:00")

    view = AllCallsView(connection, today_provider=_fixed_today)
    qtbot.addWidget(view)

    view._today_button.click()

    assert view._model.rowCount() == 1
    assert view._from_edit.date().toPython() == date(2026, 6, 15)
    assert view._to_edit.date().toPython() == date(2026, 6, 15)


def test_preset_last_7_days_sets_correct_range(qtbot, connection):
    view = AllCallsView(connection, today_provider=_fixed_today)
    qtbot.addWidget(view)

    view._last_7_days_button.click()

    assert view._from_edit.date().toPython() == date(2026, 6, 9)
    assert view._to_edit.date().toPython() == date(2026, 6, 15)


def test_preset_this_month_sets_first_of_month_to_today(qtbot, connection):
    view = AllCallsView(connection, today_provider=_fixed_today)
    qtbot.addWidget(view)

    view._this_month_button.click()

    assert view._from_edit.date().toPython() == date(2026, 6, 1)
    assert view._to_edit.date().toPython() == date(2026, 6, 15)


def test_preset_all_clears_filter_and_shows_full_history(qtbot, connection):
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_id = contacts.upsert("+491234567")
    _insert_call(calls, contact_id=contact_id, call_date="2020-01-01T10:00:00")
    _insert_call(calls, contact_id=contact_id, call_date="2026-06-15T10:00:00")

    view = AllCallsView(connection, today_provider=_fixed_today)
    qtbot.addWidget(view)
    view._today_button.click()
    assert view._model.rowCount() == 1

    view._all_button.click()

    assert view._model.rowCount() == 2


def test_manual_date_edit_activates_filter(qtbot, connection):
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_id = contacts.upsert("+491234567")
    _insert_call(calls, contact_id=contact_id, call_date="2020-01-01T10:00:00")

    view = AllCallsView(connection, today_provider=_fixed_today)
    qtbot.addWidget(view)
    assert view._model.rowCount() == 1  # kein Filter aktiv beim Start

    view._from_edit.setDate(view._from_edit.date())  # setDate mit gleichem Wert loest dateChanged nicht aus
    view._to_edit.setDate(view._to_edit.date().addDays(-1))

    assert view._model.rowCount() == 0


def test_clicking_row_emits_contact_selected_with_contact_id(qtbot, connection):
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_id = contacts.upsert("+491234567")
    _insert_call(calls, contact_id=contact_id, call_date="2026-06-01T10:00:00")

    view = AllCallsView(connection, today_provider=_fixed_today)
    qtbot.addWidget(view)

    with qtbot.waitSignal(view.contact_selected, timeout=1000) as blocker:
        view._on_row_clicked(view._model.index(0, 0))

    assert blocker.args == [contact_id]


def test_last_seen_at_is_lazily_initialized_on_first_use(qtbot, connection):
    view = AllCallsView(connection, today_provider=_fixed_today, now_provider=_fixed_now)
    qtbot.addWidget(view)

    stored = SyncStateRepository(connection).get(_LAST_SEEN_KEY)
    assert stored == _fixed_now().isoformat()
    assert view._last_seen_at == stored


def test_last_seen_at_is_not_overwritten_if_already_set(qtbot, connection):
    SyncStateRepository(connection).set(_LAST_SEEN_KEY, "2020-01-01T00:00:00")

    view = AllCallsView(connection, today_provider=_fixed_today, now_provider=_fixed_now)
    qtbot.addWidget(view)

    assert view._last_seen_at == "2020-01-01T00:00:00"


def test_existing_missed_calls_are_not_new_on_first_ever_start(qtbot, connection):
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_id = contacts.upsert("+491234567")
    _insert_call(calls, contact_id=contact_id, call_date="2020-01-01T10:00:00", call_type=2)

    view = AllCallsView(connection, today_provider=_fixed_today, now_provider=_fixed_now)
    qtbot.addWidget(view)
    view._all_button.click()

    index = view._model.index(0, 0)
    assert view._model.data(index, Qt.ItemDataRole.FontRole) is None


def test_preset_new_missed_shows_only_missed_calls_after_last_seen(qtbot, connection):
    SyncStateRepository(connection).set(_LAST_SEEN_KEY, "2026-06-10T00:00:00")
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_id = contacts.upsert("+491234567")
    _insert_call(calls, contact_id=contact_id, call_date="2026-06-05T10:00:00", call_type=2)  # alt
    _insert_call(calls, contact_id=contact_id, call_date="2026-06-12T10:00:00", call_type=1)  # neu, nicht verpasst
    _insert_call(calls, contact_id=contact_id, call_date="2026-06-13T10:00:00", call_type=2)  # neu verpasst

    view = AllCallsView(connection, today_provider=_fixed_today, now_provider=_fixed_now)
    qtbot.addWidget(view)

    view._new_missed_button.click()

    assert view._model.rowCount() == 1
    assert view._model.call_at(0).call_date == "2026-06-13T10:00:00"


def test_preset_new_missed_is_cleared_by_other_presets(qtbot, connection):
    SyncStateRepository(connection).set(_LAST_SEEN_KEY, "2026-06-10T00:00:00")
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_id = contacts.upsert("+491234567")
    _insert_call(calls, contact_id=contact_id, call_date="2026-06-15T10:00:00", call_type=1)

    view = AllCallsView(connection, today_provider=_fixed_today, now_provider=_fixed_now)
    qtbot.addWidget(view)
    view._new_missed_button.click()
    assert view._model.rowCount() == 0

    view._today_button.click()

    assert view._model.rowCount() == 1


def test_mark_seen_button_updates_timestamp_and_persists(qtbot, connection):
    view = AllCallsView(connection, today_provider=_fixed_today, now_provider=_fixed_now)
    qtbot.addWidget(view)

    view._mark_seen_button.click()

    stored = SyncStateRepository(connection).get(_LAST_SEEN_KEY)
    assert stored == _fixed_now().isoformat()
    assert view._last_seen_at == _fixed_now().isoformat()


def test_mark_seen_button_clears_highlight(qtbot, connection):
    SyncStateRepository(connection).set(_LAST_SEEN_KEY, "2026-06-01T00:00:00")
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_id = contacts.upsert("+491234567")
    _insert_call(calls, contact_id=contact_id, call_date="2026-06-05T10:00:00", call_type=2)

    view = AllCallsView(connection, today_provider=_fixed_today, now_provider=_fixed_now)
    qtbot.addWidget(view)
    view._all_button.click()
    index = view._model.index(0, 0)
    assert view._model.data(index, Qt.ItemDataRole.FontRole) is not None

    view._mark_seen_button.click()

    assert view._model.data(index, Qt.ItemDataRole.FontRole) is None


def test_new_missed_count_label_reflects_count(qtbot, connection):
    SyncStateRepository(connection).set(_LAST_SEEN_KEY, "2026-06-01T00:00:00")
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_id = contacts.upsert("+491234567")
    _insert_call(calls, contact_id=contact_id, call_date="2026-06-05T10:00:00", call_type=2)
    _insert_call(calls, contact_id=contact_id, call_date="2026-06-06T10:00:00", call_type=2)

    view = AllCallsView(connection, today_provider=_fixed_today, now_provider=_fixed_now)
    qtbot.addWidget(view)

    assert "2" in view._new_missed_count_label.text()
    assert view.new_missed_calls_count == 2


def test_new_missed_calls_changed_signal_emits_on_mark_seen(qtbot, connection):
    SyncStateRepository(connection).set(_LAST_SEEN_KEY, "2026-06-01T00:00:00")
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_id = contacts.upsert("+491234567")
    _insert_call(calls, contact_id=contact_id, call_date="2026-06-05T10:00:00", call_type=2)

    view = AllCallsView(connection, today_provider=_fixed_today, now_provider=_fixed_now)
    qtbot.addWidget(view)
    assert view.new_missed_calls_count == 1

    with qtbot.waitSignal(view.new_missed_calls_changed, timeout=1000) as blocker:
        view._mark_seen_button.click()

    assert blocker.args == [0]
