"""Qt-Modelle über der Repository-Schicht (kein Zugriff auf fritz/ oder Netzwerk)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QTableView

from fritz_callhistory.db.repository import CallRecord, CallWithContact, Contact, LocalPhonebookContact

_MISSED_CALL_TYPE = 2

# Pseudo-Call-Types fuer live per CallMonitor verfolgte, noch nicht
# synchronisierte Anrufe (siehe gui/all_calls_view.py). Bewusst ausserhalb des
# Wertebereichs echter Fritz!Box-Call-Type-Codes (>=1), damit sie z.B. nie
# versehentlich als "verpasst" gezaehlt werden.
LIVE_RINGING_CALL_TYPE = -1
LIVE_CONNECTED_CALL_TYPE = -2

_CONTACT_COLUMNS = ("Name", "Nummer", "Letzter Kontakt", "Anrufe")
_PHONEBOOK_CONTACT_COLUMNS = ("Name", "Nummern", "Notizen")
_CALL_COLUMNS = ("Datum", "Richtung", "Nummer", "Dauer", "Port/Gerät")
_ALL_CALLS_COLUMNS = ("Datum", "Richtung", "Name/Nummer", "Dauer", "Port/Gerät")

_CALL_TYPE_LABELS = {
    1: "Eingehend",
    2: "Verpasst",
    3: "Ausgehend",
    9: "Eingehend (aktiv)",
    10: "Abgelehnt",
    11: "Ausgehend (aktiv)",
    LIVE_RINGING_CALL_TYPE: "Klingelt …",
    LIVE_CONNECTED_CALL_TYPE: "Verbunden …",
}

_CALL_TYPE_ICONS = {
    1: "↘",
    2: "✕",
    3: "↗",
    9: "↘",
    10: "⊘",
    11: "↗",
    LIVE_RINGING_CALL_TYPE: "🔔",
    LIVE_CONNECTED_CALL_TYPE: "📞",
}


def _call_type_display(call_type: int) -> str:
    icon = _CALL_TYPE_ICONS.get(call_type, "")
    label = _CALL_TYPE_LABELS.get(call_type, str(call_type))
    return f"{icon} {label}" if icon else label


def call_number(call: CallRecord) -> str | None:
    """Die fuer den Nutzer relevante Nummer: bei ausgehenden Anrufen die
    angerufene, sonst die anrufende - geteilt zwischen der Tabellenanzeige
    (CallListModel) und dem Doppelklick-Handler in gui/contact_detail.py."""
    return call.called_number if call.call_type in (3, 11) else call.caller_number


def _format_call_date(call_date: str) -> str:
    """Menschenlesbares deutsches Format statt des rohen ISO8601-Zeitstempels.
    Ohne Sekunden - der Box-Zeitstempel hat ohnehin nur Minutengenauigkeit
    (siehe db/migrations/002_add_box_call_id.sql)."""
    return datetime.fromisoformat(call_date).strftime("%d.%m.%Y, %H:%M")


def port_device_display(device: str | None, port: str | None) -> str:
    """"-1" ist der Box-interne Platzhalter fuer "kein Geraet" (z.B. abgelehnte
    Anrufe) - defensiv auch hier herausfiltern, falls er je durchrutscht."""
    parts = [value for value in (device, port) if value and value != "-1"]
    return " / ".join(parts) or "-"


def _format_duration(duration_seconds: int | None) -> str:
    if duration_seconds is None:
        return "-"
    minutes, seconds = divmod(duration_seconds, 60)
    return f"{minutes}:{seconds:02d}"


class _SimpleTableModel(QAbstractTableModel):
    """Gemeinsames rowCount/columnCount/headerData für Modelle, die eine flache
    Liste von Items über feste Spaltennamen (Klassenattribut _columns)
    anzeigen. Subklassen implementieren nur noch data()."""

    _columns: tuple[str, ...] = ()

    def __init__(self, items: list | None = None) -> None:
        super().__init__()
        self._items: list = items or []

    def _set_items(self, items: list) -> None:
        self.beginResetModel()
        self._items = items
        self.endResetModel()

    def _item_at(self, row: int):
        return self._items[row]

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._items)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._columns)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole or orientation != Qt.Orientation.Horizontal:
            return None
        return self._columns[section]


class ContactListModel(_SimpleTableModel):
    _columns = _CONTACT_COLUMNS

    def __init__(self, contacts: list[Contact] | None = None) -> None:
        super().__init__(contacts)

    def set_contacts(self, contacts: list[Contact]) -> None:
        self._set_items(contacts)

    def contact_at(self, row: int) -> Contact:
        return self._item_at(row)

    def index_of(self, contact_id: int) -> int | None:
        for row, contact in enumerate(self._items):
            if contact.id == contact_id:
                return row
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        contact = self._items[index.row()]
        column = index.column()
        if column == 0:
            if contact.is_anonymous:
                return "Anonym / unterdrückt"
            return contact.display_name or "Unbekannt"
        if column == 1:
            return contact.primary_number
        if column == 2:
            return _format_call_date(contact.last_call_date) if contact.last_call_date else "-"
        if column == 3:
            return str(contact.call_count)
        return None


class PhonebookContactListModel(_SimpleTableModel):
    """Lokales Telefonbuch (gui/phonebook_view.py) - Mehrfachnummern pro Kontakt."""

    _columns = _PHONEBOOK_CONTACT_COLUMNS

    def __init__(self, contacts: list[LocalPhonebookContact] | None = None) -> None:
        super().__init__(contacts)

    def set_contacts(self, contacts: list[LocalPhonebookContact]) -> None:
        self._set_items(contacts)

    def contact_at(self, row: int) -> LocalPhonebookContact:
        return self._item_at(row)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        contact = self._items[index.row()]
        column = index.column()
        if column == 0:
            return contact.display_name
        if column == 1:
            if not contact.numbers:
                return "-"
            return ", ".join(f"{n.number_raw} ({n.number_type})" for n in contact.numbers)
        if column == 2:
            return contact.notes or "-"
        return None


class CallListModel(_SimpleTableModel):
    """Chronologische Anrufliste für einen einzelnen Kontakt (Detailansicht)."""

    _columns = _CALL_COLUMNS

    def __init__(self, calls: list[CallRecord] | None = None) -> None:
        super().__init__(calls)

    def set_calls(self, calls: list[CallRecord]) -> None:
        self._set_items(calls)

    def call_at(self, row: int) -> CallRecord:
        return self._item_at(row)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        call = self._items[index.row()]
        column = index.column()
        if column == 0:
            return _format_call_date(call.call_date)
        if column == 1:
            return _call_type_display(call.call_type)
        if column == 2:
            return call_number(call)
        if column == 3:
            return _format_duration(call.duration_seconds)
        if column == 4:
            return port_device_display(call.device, call.port)
        return None


class AllCallsListModel(_SimpleTableModel):
    """Chronologische Anrufliste ueber alle Kontakte hinweg ("Alle Anrufe").

    Hebt neue verpasste Anrufe (call_date > last_seen_at) optisch hervor,
    unabhaengig vom aktuell aktiven Datumsfilter/Preset in AllCallsView.
    """

    _columns = _ALL_CALLS_COLUMNS

    def __init__(
        self,
        calls: list[CallWithContact] | None = None,
        last_seen_at: str | None = None,
    ) -> None:
        super().__init__(calls)
        self._last_seen_at = last_seen_at

    def set_calls(self, calls: list[CallWithContact]) -> None:
        self._set_items(calls)

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
        return self._item_at(row)

    def _is_new_missed(self, call: CallWithContact) -> bool:
        return (
            call.call_type == _MISSED_CALL_TYPE
            and self._last_seen_at is not None
            and call.call_date > self._last_seen_at
        )

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        call = self._items[index.row()]
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
            return _format_call_date(call.call_date)
        if column == 1:
            return _call_type_display(call.call_type)
        if column == 2:
            if call.contact_is_anonymous:
                return "Anonym / unterdrückt"
            return call.contact_display_name or call.contact_primary_number
        if column == 3:
            return _format_duration(call.duration_seconds)
        if column == 4:
            return port_device_display(call.device, call.port)
        return None


class DataclassSortProxy(QSortFilterProxyModel):
    """Sortiert nach typisierten Feldern der Quell-Dataclass statt der
    angezeigten Text-Repraesentation (verhindert z.B. lexikographische
    Fehlsortierung bei 'm:ss'-Dauer oder Anrufzahlen). row_getter ist die
    bestehende contact_at()/call_at()-Methode des Quellmodells; key_fns bildet
    Spaltenindex auf eine Funktion ab, die aus der Zeile einen vergleichbaren
    Schluessel extrahiert. Spalten ohne Eintrag fallen auf den Standard-
    Textvergleich zurueck."""

    def __init__(
        self,
        row_getter: Callable[[int], Any],
        key_fns: dict[int, Callable[[Any], Any]],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._row_getter = row_getter
        self._key_fns = key_fns

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        key_fn = self._key_fns.get(left.column())
        if key_fn is None:
            return super().lessThan(left, right)
        a = key_fn(self._row_getter(left.row()))
        b = key_fn(self._row_getter(right.row()))
        if a is None:
            return True
        if b is None:
            return False
        return a < b


def install_tristate_sorting(table: QTableView, proxy: QSortFilterProxyModel) -> None:
    """Klick 1: aufsteigend, Klick 2: absteigend, Klick 3: zurueck zur
    Ausgangsreihenfolge. QTableView.setSortingEnabled(True) allein bietet nur
    einen 2-stufigen Toggle (auf-/absteigend), daher hier manuell per
    sectionClicked verwaltet."""
    header = table.horizontalHeader()
    header.setSectionsClickable(True)
    header.setSortIndicatorShown(False)
    state = {"column": -1, "order": Qt.SortOrder.AscendingOrder}

    def on_section_clicked(column: int) -> None:
        if state["column"] != column:
            state["column"], state["order"] = column, Qt.SortOrder.AscendingOrder
        elif state["order"] == Qt.SortOrder.AscendingOrder:
            state["order"] = Qt.SortOrder.DescendingOrder
        else:
            state["column"] = -1
        if state["column"] == -1:
            header.setSortIndicatorShown(False)
            proxy.sort(-1)
        else:
            header.setSortIndicatorShown(True)
            header.setSortIndicator(state["column"], state["order"])
            proxy.sort(state["column"], state["order"])

    header.sectionClicked.connect(on_section_clicked)
