"""Qt-Modelle über der Repository-Schicht (kein Zugriff auf fritz/ oder Netzwerk)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QLineEdit, QMenu, QTableView

from fritz_callhistory.db.repository import (
    CallRecord,
    CallWithContact,
    Contact,
    LocalPhonebookContact,
    VoicemailMessageRecord,
)
from fritz_callhistory.sync.normalize import format_number_display

_MISSED_CALL_TYPE = 2

# Pseudo-Call-Types für live per CallMonitor verfolgte, noch nicht
# synchronisierte Anrufe (siehe gui/all_calls_view.py). Bewusst ausserhalb des
# Wertebereichs echter Fritz!Box-Call-Type-Codes (>=1), damit sie z.B. nie
# versehentlich als "verpasst" gezählt werden.
LIVE_RINGING_CALL_TYPE = -1
LIVE_CONNECTED_CALL_TYPE = -2

_CONTACT_COLUMNS = ("Name", "Letzter Kontakt", "Anrufe")
_PHONEBOOK_CONTACT_COLUMNS = ("Name", "Nummern", "Notizen")
_CALL_COLUMNS = ("Datum", "Richtung", "Nummer", "Dauer", "Port/Gerät")
_ALL_CALLS_COLUMNS = ("Datum", "Richtung", "Name/Nummer", "Dauer", "Port/Gerät")
_VOICEMAIL_COLUMNS = ("Datum", "Anrufer", "Dauer")

# Nur für reguläre Anrufe (CallListModel/AllCallsListModel) - die Box liefert deren
# Datum/Dauer ohnehin nur mit Minutengenauigkeit (siehe _format_call_date und
# fritz/client.py's _parse_duration_seconds-Docstring). Bewusst nicht für
# VoicemailListModel: dessen "Dauer"-Spalte hat echte Sekundengenauigkeit.
_MINUTE_PRECISION_TOOLTIPS = {
    "Datum": "Zeitstempel der Fritz!Box haben nur Minutengenauigkeit (keine Sekunden)",
    "Dauer": "Die Fritz!Box liefert die Gesprächsdauer nur in ganzen Minuten (keine Sekunden)",
}

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
    """Die für den Nutzer relevante Nummer: bei ausgehenden Anrufen die
    angerufene, sonst die anrufende - geteilt zwischen der Tabellenanzeige
    (CallListModel) und dem Doppelklick-Handler in gui/contact_detail.py."""
    return call.called_number if call.call_type in (3, 11) else call.caller_number


def _format_call_date(call_date: str) -> str:
    """Menschenlesbares deutsches Format statt des rohen ISO8601-Zeitstempels.
    Ohne Sekunden - der Box-Zeitstempel hat ohnehin nur Minutengenauigkeit
    (siehe db/migrations/002_add_box_call_id.sql)."""
    return datetime.fromisoformat(call_date).strftime("%d.%m.%Y, %H:%M")


def port_device_display(device: str | None, port: str | None) -> str:
    """"-1" ist der Box-interne Platzhalter für "kein Gerät" (z.B. abgelehnte
    Anrufe) - defensiv auch hier herausfiltern, falls er je durchrutscht."""
    parts = [value for value in (device, port) if value and value != "-1"]
    return " / ".join(parts) or "-"


def _format_duration(duration_seconds: int | None) -> str:
    if duration_seconds is None:
        return "-"
    minutes, seconds = divmod(duration_seconds, 60)
    return f"{minutes}:{seconds:02d}"


def contact_display_label(is_anonymous: bool, display_name: str | None, fallback: str = "Unbekannt") -> str:
    """Anzeigename eines Kontakts - geteilt zwischen ContactListModel,
    AllCallsListModel und gui/contact_detail.py's show_contact(). *fallback*
    greift, wenn kein Anzeigename bekannt ist (bei AllCallsListModel die
    Rufnummer statt "Unbekannt", da dort immer eine Nummer vorliegt)."""
    if is_anonymous:
        return "Anonym / unterdrückt"
    return display_name or fallback


class _SimpleTableModel(QAbstractTableModel):
    """Gemeinsames rowCount/columnCount/headerData für Modelle, die eine flache
    Liste von Items über feste Spaltennamen (Klassenattribut _columns)
    anzeigen. Subklassen implementieren nur noch data()."""

    _columns: tuple[str, ...] = ()
    # Optional Spaltenname -> Tooltip-Text, von Subklassen gezielt gesetzt (nicht
    # alle Modelle mit einer gleichnamigen Spalte teilen dieselbe Einschraenkung -
    # z.B. hat VoicemailListModel ebenfalls eine "Dauer"-Spalte, aber dort liefert
    # die Box echte Sekundengenauigkeit, siehe fritz/client.py's _parse_duration_seconds).
    _header_tooltips: dict[str, str] = {}

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
        if orientation != Qt.Orientation.Horizontal:
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return self._columns[section]
        if role == Qt.ItemDataRole.ToolTipRole:
            return self._header_tooltips.get(self._columns[section])
        return None


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
            return contact_display_label(contact.is_anonymous, contact.display_name)
        if column == 1:
            return _format_call_date(contact.last_call_date) if contact.last_call_date else "-"
        if column == 2:
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
            return ", ".join(
                f"{format_number_display(n.number_raw)} ({n.number_type})" for n in contact.numbers
            )
        if column == 2:
            return contact.notes or "-"
        return None


class CallListModel(_SimpleTableModel):
    """Chronologische Anrufliste für einen einzelnen Kontakt (Detailansicht)."""

    _columns = _CALL_COLUMNS
    _header_tooltips = _MINUTE_PRECISION_TOOLTIPS

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
            return format_number_display(call_number(call))
        if column == 3:
            return _format_duration(call.duration_seconds)
        if column == 4:
            return port_device_display(call.device, call.port)
        return None


class AllCallsListModel(_SimpleTableModel):
    """Chronologische Anrufliste über alle Kontakte hinweg ("Alle Anrufe").

    Hebt neue verpasste Anrufe (call_date > last_seen_at) optisch hervor,
    unabhängig vom aktuell aktiven Datumsfilter/Preset in AllCallsView.
    """

    _columns = _ALL_CALLS_COLUMNS
    _header_tooltips = _MINUTE_PRECISION_TOOLTIPS

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
            return contact_display_label(
                call.contact_is_anonymous,
                call.contact_display_name,
                format_number_display(call.contact_primary_number),
            )
        if column == 3:
            return _format_duration(call.duration_seconds)
        if column == 4:
            return port_device_display(call.device, call.port)
        return None


def voicemail_caller_display(message: VoicemailMessageRecord) -> str:
    if message.raw_name:
        return message.raw_name
    if message.caller_number:
        return format_number_display(message.caller_number)
    return "Anonym / unterdrückt"


class VoicemailListModel(_SimpleTableModel):
    """Anrufbeantworter-Nachrichtenliste ("Anrufbeantworter"-Tab).

    Hebt neue (noch nicht gehörte) Nachrichten optisch hervor, direkt anhand des
    Box-eigenen is_new-Flags - anders als bei AllCallsListModel wird hier kein
    lokal verfolgtes last_seen_at gebraucht, die Box ist für "neu/gehört" allein
    massgeblich (siehe VoicemailRepository.insert_or_update)."""

    _columns = _VOICEMAIL_COLUMNS

    def __init__(self, messages: list[VoicemailMessageRecord] | None = None) -> None:
        super().__init__(messages)

    def set_messages(self, messages: list[VoicemailMessageRecord]) -> None:
        self._set_items(messages)

    def message_at(self, row: int) -> VoicemailMessageRecord:
        return self._item_at(row)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        message = self._items[index.row()]
        if role == Qt.ItemDataRole.FontRole and message.is_new:
            font = QFont()
            font.setBold(True)
            return font
        if role == Qt.ItemDataRole.ForegroundRole and message.is_new:
            return QColor(Qt.GlobalColor.red)
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        column = index.column()
        if column == 0:
            return _format_call_date(message.message_date)
        if column == 1:
            return voicemail_caller_display(message)
        if column == 2:
            return _format_duration(message.duration_seconds)
        return None


class DataclassSortProxy(QSortFilterProxyModel):
    """Sortiert nach typisierten Feldern der Quell-Dataclass statt der
    angezeigten Text-Repräsentation (verhindert z.B. lexikographische
    Fehlsortierung bei 'm:ss'-Dauer oder Anrufzahlen). row_getter ist die
    bestehende contact_at()/call_at()-Methode des Quellmodells; key_fns bildet
    Spaltenindex auf eine Funktion ab, die aus der Zeile einen vergleichbaren
    Schlüssel extrahiert. Spalten ohne Eintrag fallen auf den Standard-
    Textvergleich zurück."""

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
    """Klick 1: aufsteigend, Klick 2: absteigend, Klick 3: zurück zur
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


def install_debounced_search(
    line_edit: QLineEdit,
    callback: Callable[[], None],
    interval_ms: int = 250,
) -> QTimer:
    """Verzögert callback() um interval_ms nach der letzten Texteingabe in
    line_edit (verhindert einen DB-Query pro Tastenanschlag). Gibt den Timer
    zurück, damit Tests ihn direkt triggern können (timer.timeout.emit())."""
    timer = QTimer(line_edit)
    timer.setSingleShot(True)
    timer.setInterval(interval_ms)
    timer.timeout.connect(callback)
    line_edit.textChanged.connect(lambda _: timer.start())
    return timer


def selected_source_row(table: QTableView, proxy: QSortFilterProxyModel) -> int | None:
    """Source-Model-Zeile der aktuellen (Einzel-)Auswahl von *table*, oder None,
    wenn nichts ausgewählt ist - fasst das Muster zusammen, das bereits einzeln
    in phonebook_view.py's _selected_contact_id() und voicemail_view.py's
    _selected_message() steckt, für Views, die noch keine solche Helper-Methode
    haben (siehe deren dial_selected())."""
    indexes = table.selectionModel().selectedRows()
    if not indexes:
        return None
    return proxy.mapToSource(indexes[0]).row()


def default_or_first_number(contact: LocalPhonebookContact) -> str | None:
    """Nummer, die eine "Anrufen"-Aktion ohne weitere Auswahl verwenden soll:
    die als Standard markierte, sonst die erste - dieselbe Priorität wie das
    Kontextmenü (install_phonebook_call_context_menu unten)."""
    numbers = contact.numbers
    if not numbers:
        return None
    default = next((n for n in numbers if n.is_default), None)
    return (default or numbers[0]).number_normalized


def install_call_context_menu(
    table: QTableView,
    proxy: QSortFilterProxyModel,
    number_for_row: Callable[[int], str | None],
    on_call: Callable[[str], None],
) -> None:
    """Rechtsklick-Kontextmenü mit einem "Anrufen"-Eintrag für die Zeile unter
    dem Mauszeiger. *number_for_row* liefert None, wenn die Zeile keine
    anrufbare Nummer hat (z.B. anonym/unterdrückt oder ein noch laufender
    Live-Anruf) - dann erscheint gar kein Menü."""
    table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

    def on_context_menu(pos) -> None:
        index = table.indexAt(pos)
        if not index.isValid():
            return
        number = number_for_row(proxy.mapToSource(index).row())
        if not number:
            return
        menu = QMenu(table)
        menu.addAction(f"Anrufen: {format_number_display(number)}").triggered.connect(
            lambda: on_call(number)
        )
        menu.exec(table.viewport().mapToGlobal(pos))

    table.customContextMenuRequested.connect(on_context_menu)


def install_phonebook_call_context_menu(
    table: QTableView,
    proxy: QSortFilterProxyModel,
    contact_at: Callable[[int], LocalPhonebookContact],
    on_call: Callable[[str], None],
) -> None:
    """Wie install_call_context_menu, aber für Telefonbuch-Kontakte mit
    potenziell mehreren Nummern: 0 Nummern -> kein Menü, 1 Nummer -> ein
    "Anrufen: <Nummer>"-Eintrag, 2+ ohne Standardnummer -> "Anrufen"-Untermenü
    mit je einem Eintrag pro Nummer, 2+ mit Standardnummer -> zwei Top-Level-
    Einträge ("Standardnummer anrufen" + "Nummer auswählen"-Untermenü).
    Wählt stets die normalisierte Nummer (nicht die roh eingegebene), damit
    der Wählhilfe kein nutzerformatierter Freitext übergeben wird."""
    table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

    def on_context_menu(pos) -> None:
        index = table.indexAt(pos)
        if not index.isValid():
            return
        contact = contact_at(proxy.mapToSource(index).row())
        numbers = contact.numbers
        if not numbers:
            return
        menu = QMenu(table)
        if len(numbers) == 1:
            number = numbers[0]
            menu.addAction(f"Anrufen: {format_number_display(number.number_raw)}").triggered.connect(
                lambda: on_call(number.number_normalized)
            )
        else:
            default = next((n for n in numbers if n.is_default), None)
            if default is not None:
                menu.addAction(
                    f"Standardnummer anrufen: {format_number_display(default.number_raw)}"
                ).triggered.connect(lambda: on_call(default.number_normalized))
                submenu = menu.addMenu("Nummer auswählen")
            else:
                submenu = menu.addMenu("Anrufen")
            for n in numbers:
                submenu.addAction(format_number_display(n.number_raw)).triggered.connect(
                    lambda checked=False, num=n.number_normalized: on_call(num)
                )
        menu.exec(table.viewport().mapToGlobal(pos))

    table.customContextMenuRequested.connect(on_context_menu)


