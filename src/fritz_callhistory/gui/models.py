"""Qt-Modelle über der Repository-Schicht (kein Zugriff auf fritz/ oder Netzwerk)."""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor, QFont

from fritz_callhistory.db.repository import CallRecord, CallWithContact, Contact

_MISSED_CALL_TYPE = 2

_CONTACT_COLUMNS = ("Name", "Nummer", "Letzter Kontakt", "Anrufe")
_CALL_COLUMNS = ("Datum", "Richtung", "Nummer", "Dauer", "Port/Gerät")
_ALL_CALLS_COLUMNS = ("Datum", "Richtung", "Name/Nummer", "Dauer", "Port/Gerät")

_CALL_TYPE_LABELS = {
    1: "Eingehend",
    2: "Verpasst",
    3: "Ausgehend",
    9: "Eingehend (aktiv)",
    10: "Abgelehnt",
    11: "Ausgehend (aktiv)",
}

_CALL_TYPE_ICONS = {
    1: "↘",
    2: "✕",
    3: "↗",
    9: "↘",
    10: "⊘",
    11: "↗",
}


def _call_type_display(call_type: int) -> str:
    icon = _CALL_TYPE_ICONS.get(call_type, "")
    label = _CALL_TYPE_LABELS.get(call_type, str(call_type))
    return f"{icon} {label}" if icon else label


class ContactListModel(QAbstractTableModel):
    def __init__(self, contacts: list[Contact] | None = None) -> None:
        super().__init__()
        self._contacts: list[Contact] = contacts or []

    def set_contacts(self, contacts: list[Contact]) -> None:
        self.beginResetModel()
        self._contacts = contacts
        self.endResetModel()

    def contact_at(self, row: int) -> Contact:
        return self._contacts[row]

    def index_of(self, contact_id: int) -> int | None:
        for row, contact in enumerate(self._contacts):
            if contact.id == contact_id:
                return row
        return None

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._contacts)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(_CONTACT_COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole or orientation != Qt.Orientation.Horizontal:
            return None
        return _CONTACT_COLUMNS[section]

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        contact = self._contacts[index.row()]
        column = index.column()
        if column == 0:
            if contact.is_anonymous:
                return "Anonym / unterdrückt"
            return contact.display_name or "Unbekannt"
        if column == 1:
            return contact.primary_number
        if column == 2:
            return contact.last_call_date or "-"
        if column == 3:
            return str(contact.call_count)
        return None


class CallListModel(QAbstractTableModel):
    """Chronologische Anrufliste für einen einzelnen Kontakt (Detailansicht)."""

    def __init__(self, calls: list[CallRecord] | None = None) -> None:
        super().__init__()
        self._calls: list[CallRecord] = calls or []

    def set_calls(self, calls: list[CallRecord]) -> None:
        self.beginResetModel()
        self._calls = calls
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._calls)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(_CALL_COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole or orientation != Qt.Orientation.Horizontal:
            return None
        return _CALL_COLUMNS[section]

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        call = self._calls[index.row()]
        column = index.column()
        if column == 0:
            return call.call_date
        if column == 1:
            return _call_type_display(call.call_type)
        if column == 2:
            return call.called_number if call.call_type in (3, 11) else call.caller_number
        if column == 3:
            if call.duration_seconds is None:
                return "-"
            minutes, seconds = divmod(call.duration_seconds, 60)
            return f"{minutes}:{seconds:02d}"
        if column == 4:
            return " / ".join(filter(None, [call.device, call.port])) or "-"
        return None


class AllCallsListModel(QAbstractTableModel):
    """Chronologische Anrufliste ueber alle Kontakte hinweg ("Alle Anrufe").

    Hebt neue verpasste Anrufe (call_date > last_seen_at) optisch hervor,
    unabhaengig vom aktuell aktiven Datumsfilter/Preset in AllCallsView.
    """

    def __init__(
        self,
        calls: list[CallWithContact] | None = None,
        last_seen_at: str | None = None,
    ) -> None:
        super().__init__()
        self._calls: list[CallWithContact] = calls or []
        self._last_seen_at = last_seen_at

    def set_calls(self, calls: list[CallWithContact]) -> None:
        self.beginResetModel()
        self._calls = calls
        self.endResetModel()

    def set_last_seen_at(self, last_seen_at: str | None) -> None:
        self._last_seen_at = last_seen_at
        if self.rowCount() and self.columnCount():
            top_left = self.index(0, 0)
            bottom_right = self.index(self.rowCount() - 1, self.columnCount() - 1)
            self.dataChanged.emit(
                top_left,
                bottom_right,
                [Qt.ItemDataRole.FontRole, Qt.ItemDataRole.ForegroundRole],
            )

    def call_at(self, row: int) -> CallWithContact:
        return self._calls[row]

    def _is_new_missed(self, call: CallWithContact) -> bool:
        return (
            call.call_type == _MISSED_CALL_TYPE
            and self._last_seen_at is not None
            and call.call_date > self._last_seen_at
        )

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._calls)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(_ALL_CALLS_COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole or orientation != Qt.Orientation.Horizontal:
            return None
        return _ALL_CALLS_COLUMNS[section]

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        call = self._calls[index.row()]
        if role == Qt.ItemDataRole.FontRole and self._is_new_missed(call):
            font = QFont()
            font.setBold(True)
            return font
        if role == Qt.ItemDataRole.ForegroundRole and self._is_new_missed(call):
            return QColor(Qt.GlobalColor.red)
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        column = index.column()
        if column == 0:
            return call.call_date
        if column == 1:
            return _call_type_display(call.call_type)
        if column == 2:
            if call.contact_is_anonymous:
                return "Anonym / unterdrückt"
            return call.contact_display_name or call.contact_primary_number
        if column == 3:
            if call.duration_seconds is None:
                return "-"
            minutes, seconds = divmod(call.duration_seconds, 60)
            return f"{minutes}:{seconds:02d}"
        if column == 4:
            return " / ".join(filter(None, [call.device, call.port])) or "-"
        return None
