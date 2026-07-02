import pytest
from PySide6.QtCore import Qt

from fritz_callhistory.db.repository import CallRecord, CallWithContact
from fritz_callhistory.gui.models import AllCallsListModel, CallListModel


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
