"""Qt-Modelle über der Repository-Schicht (kein Zugriff auf fritz/ oder Netzwerk)."""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from fritz_callhistory.db.repository import CallRecord, Contact

_CONTACT_COLUMNS = ("Name", "Nummer", "Letzter Kontakt", "Anrufe")
_CALL_COLUMNS = ("Datum", "Richtung", "Nummer", "Dauer", "Port/Gerät")

_CALL_TYPE_LABELS = {
    1: "Eingehend",
    2: "Verpasst",
    3: "Ausgehend",
    9: "Eingehend (aktiv)",
    10: "Abgelehnt",
    11: "Ausgehend (aktiv)",
}


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
            return _CALL_TYPE_LABELS.get(call.call_type, str(call.call_type))
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
