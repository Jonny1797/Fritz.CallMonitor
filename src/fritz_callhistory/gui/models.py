"""Qt-Modelle über der Repository-Schicht (kein Zugriff auf fritz/ oder Netzwerk)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QHeaderView, QLineEdit, QMenu, QTableView, QWidget

from fritz_callhistory.db.repository import (
    CallRecord,
    CallWithContact,
    Contact,
    LocalPhonebookContact,
    VoicemailMessageRecord,
)
from fritz_callhistory.fritz.call_types import counterparty_number, is_missed
from fritz_callhistory.fritz.call_types import display as call_type_display
from fritz_callhistory.gui.live_calls import LiveCall, LiveCallState
from fritz_callhistory.sync.caller_directory import CallerIdentity
from fritz_callhistory.sync.normalize import format_number_display, normalize_number

# Nur für reguläre Anrufe (CallListModel/AllCallsListModel) - die Box liefert deren
# Datum/Dauer ohnehin nur mit Minutengenauigkeit (siehe _format_call_date und
# fritz/client.py's _parse_duration_seconds-Docstring). Bewusst nicht für
# VoicemailListModel: dessen "Dauer"-Spalte hat echte Sekundengenauigkeit.
_MINUTE_PRECISION_TOOLTIPS = {
    "Datum": "Zeitstempel der Fritz!Box haben nur Minutengenauigkeit (keine Sekunden)",
    "Dauer": "Die Fritz!Box liefert die Gesprächsdauer nur in ganzen Minuten (keine Sekunden)",
}

def call_number(call: CallRecord) -> str | None:
    """Die für den Nutzer relevante Nummer: bei ausgehenden Anrufen die
    angerufene, sonst die anrufende - geteilt zwischen der Tabellenanzeige
    (CallListModel) und dem Doppelklick-Handler in gui/contact_detail.py."""
    return counterparty_number(call.call_type, call.caller_number, call.called_number)


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


@dataclass(frozen=True)
class Column:
    """Eine Tabellenspalte, einmal definiert: Kopfzeile, Anzeigetext, Sortier-
    schlüssel und Tooltip. *sort_key* None -> die Spalte sortiert nach ihrem
    Anzeigetext."""

    id: str
    header: str
    display: Callable[[Any], str]
    sort_key: Callable[[Any], Any] | None = None
    tooltip: str | None = None

    def key(self, row: Any) -> Any:
        return self.sort_key(row) if self.sort_key is not None else self.display(row)


def _contact_name(contact: Contact) -> str:
    return contact_display_label(contact.is_anonymous, contact.display_name)


def _phonebook_numbers(contact: LocalPhonebookContact) -> str:
    if not contact.numbers:
        return "-"
    return ", ".join(
        f"{format_number_display(n.number_raw)} ({n.number_type})" for n in contact.numbers
    )


def _call_number_display(call: CallRecord) -> str:
    return format_number_display(call_number(call))


def _call_number_sort_key(call: CallRecord) -> str:
    return normalize_number(call_number(call))[0]


AllCallsRow = CallWithContact | LiveCall

_LIVE_STATE_ORDER = {
    LiveCallState.CONNECTED: 0,
    LiveCallState.RINGING: 1,
    LiveCallState.ENDED: 2,
}


def _all_calls_name(row: AllCallsRow) -> str:
    if isinstance(row, LiveCall):
        identity = row.identity
        return contact_display_label(
            identity.is_anonymous, identity.name, format_number_display(identity.number)
        )
    return contact_display_label(
        row.contact_is_anonymous,
        row.contact_display_name,
        format_number_display(row.contact_primary_number),
    )


def _all_calls_date_raw(row: AllCallsRow) -> str:
    return row.started_at if isinstance(row, LiveCall) else row.call_date


def _all_calls_date(row: AllCallsRow) -> str:
    return _format_call_date(_all_calls_date_raw(row))


def _all_calls_direction(row: AllCallsRow) -> str:
    if isinstance(row, LiveCall):
        return row.display()
    return call_type_display(row.call_type)


def _all_calls_direction_key(row: AllCallsRow) -> tuple[int, int]:
    """Live-Anrufe sortieren vor allen Box-Codes."""
    if isinstance(row, LiveCall):
        return (0, _LIVE_STATE_ORDER[row.state])
    return (1, row.call_type)


def _all_calls_duration_seconds(row: AllCallsRow) -> int | None:
    return None if isinstance(row, LiveCall) else row.duration_seconds


def _all_calls_duration(row: AllCallsRow) -> str:
    return _format_duration(_all_calls_duration_seconds(row))


def _all_calls_port_device(row: AllCallsRow) -> str:
    if isinstance(row, LiveCall):
        return port_device_display(None, None)
    return port_device_display(row.device, row.port)


def _call_columns(number: Column) -> tuple[Column, ...]:
    return (
        Column(
            "date",
            "Datum",
            lambda c: _format_call_date(c.call_date),
            lambda c: c.call_date,
            _MINUTE_PRECISION_TOOLTIPS["Datum"],
        ),
        Column("direction", "Richtung", lambda c: call_type_display(c.call_type), lambda c: c.call_type),
        number,
        Column(
            "duration",
            "Dauer",
            lambda c: _format_duration(c.duration_seconds),
            lambda c: c.duration_seconds,
            _MINUTE_PRECISION_TOOLTIPS["Dauer"],
        ),
        Column(
            "port_device",
            "Port/Gerät",
            lambda c: port_device_display(c.device, c.port),
        ),
    )


CONTACT_COLUMNS = (
    Column("name", "Name", _contact_name, lambda c: _contact_name(c).lower()),
    Column(
        "last_call",
        "Letzter Kontakt",
        lambda c: _format_call_date(c.last_call_date) if c.last_call_date else "-",
        lambda c: c.last_call_date,
    ),
    Column("call_count", "Anrufe", lambda c: str(c.call_count), lambda c: c.call_count),
)

PHONEBOOK_COLUMNS = (
    Column(
        "name",
        "Name",
        lambda c: c.display_name,
        lambda c: (c.display_name or "").lower(),
    ),
    Column(
        "numbers",
        "Nummern",
        _phonebook_numbers,
        lambda c: c.numbers[0].number_normalized if c.numbers else "",
    ),
    Column("notes", "Notizen", lambda c: c.notes or "-", lambda c: c.notes or ""),
)

CALL_COLUMNS = _call_columns(
    Column("number", "Nummer", _call_number_display, _call_number_sort_key)
)

ALL_CALLS_COLUMNS = (
    Column(
        "date",
        "Datum",
        _all_calls_date,
        _all_calls_date_raw,
        _MINUTE_PRECISION_TOOLTIPS["Datum"],
    ),
    Column("direction", "Richtung", _all_calls_direction, _all_calls_direction_key),
    Column("name_number", "Name/Nummer", _all_calls_name, lambda r: _all_calls_name(r).lower()),
    Column(
        "duration",
        "Dauer",
        _all_calls_duration,
        _all_calls_duration_seconds,
        _MINUTE_PRECISION_TOOLTIPS["Dauer"],
    ),
    Column("port_device", "Port/Gerät", _all_calls_port_device),
)


def voicemail_columns(caller_label: Callable[[VoicemailMessageRecord], str]) -> tuple[Column, ...]:
    """Anrufbeantworter-Spalten; *caller_label* liefert den Anzeigenamen je
    Nachricht (kommt aus dem Caller directory, daher nicht Teil der Zeile)."""
    return (
        Column(
            "date",
            "Datum",
            lambda m: _format_call_date(m.message_date),
            lambda m: m.message_date,
        ),
        Column("caller", "Anrufer", caller_label, lambda m: caller_label(m).lower()),
        Column(
            "duration",
            "Dauer",
            lambda m: _format_duration(m.duration_seconds),
            lambda m: m.duration_seconds,
        ),
    )


class TableModel(QAbstractTableModel):
    """Generisches Tabellenmodell aus einem Column-Tupel und einer flachen
    Zeilenliste. *row_emphasis* markiert Zeilen, die fett/rot dargestellt werden."""

    def __init__(
        self,
        columns: tuple[Column, ...],
        items: list | None = None,
        row_emphasis: Callable[[Any], bool] | None = None,
    ) -> None:
        super().__init__()
        self._columns = columns
        self._items: list = items or []
        self._row_emphasis = row_emphasis

    @property
    def columns(self) -> tuple[Column, ...]:
        return self._columns

    def column_id(self, column: int) -> str:
        return self._columns[column].id

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
            return self._columns[section].header
        if role == Qt.ItemDataRole.ToolTipRole:
            return self._columns[section].tooltip
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self._items[index.row()]
        if role in (Qt.ItemDataRole.FontRole, Qt.ItemDataRole.ForegroundRole):
            if self._row_emphasis is None or not self._row_emphasis(row):
                return None
            if role == Qt.ItemDataRole.FontRole:
                font = QFont()
                font.setBold(True)
                return font
            return QColor(Qt.GlobalColor.red)
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        return self._columns[index.column()].display(row)


class ContactListModel(TableModel):
    def __init__(self, contacts: list[Contact] | None = None) -> None:
        super().__init__(CONTACT_COLUMNS, contacts)

    def set_contacts(self, contacts: list[Contact]) -> None:
        self._set_items(contacts)

    def contact_at(self, row: int) -> Contact:
        return self._item_at(row)

    def index_of(self, contact_id: int) -> int | None:
        for row, contact in enumerate(self._items):
            if contact.id == contact_id:
                return row
        return None


class PhonebookContactListModel(TableModel):
    """Lokales Telefonbuch (gui/phonebook_view.py) - Mehrfachnummern pro Kontakt."""

    def __init__(self, contacts: list[LocalPhonebookContact] | None = None) -> None:
        super().__init__(PHONEBOOK_COLUMNS, contacts)

    def set_contacts(self, contacts: list[LocalPhonebookContact]) -> None:
        self._set_items(contacts)

    def contact_at(self, row: int) -> LocalPhonebookContact:
        return self._item_at(row)


class CallListModel(TableModel):
    """Chronologische Anrufliste für einen einzelnen Kontakt (Detailansicht)."""

    def __init__(self, calls: list[CallRecord] | None = None) -> None:
        super().__init__(CALL_COLUMNS, calls)

    def set_calls(self, calls: list[CallRecord]) -> None:
        self._set_items(calls)

    def call_at(self, row: int) -> CallRecord:
        return self._item_at(row)


class AllCallsListModel(TableModel):
    """Chronologische Anrufliste über alle Kontakte hinweg ("Alle Anrufe").

    Hebt neue verpasste Anrufe (call_date > last_seen_at) optisch hervor,
    unabhängig vom aktuell aktiven Datumsfilter/Preset in AllCallsView.
    """

    def __init__(
        self,
        calls: list[AllCallsRow] | None = None,
        last_seen_at: str | None = None,
    ) -> None:
        super().__init__(ALL_CALLS_COLUMNS, calls, row_emphasis=self._is_new_missed)
        self._last_seen_at = last_seen_at

    def set_calls(self, calls: list[AllCallsRow]) -> None:
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

    def call_at(self, row: int) -> AllCallsRow:
        return self._item_at(row)

    def _is_new_missed(self, call: AllCallsRow) -> bool:
        if isinstance(call, LiveCall):
            return call.is_new_missed(self._last_seen_at)
        return (
            is_missed(call.call_type)
            and self._last_seen_at is not None
            and call.call_date > self._last_seen_at
        )


def voicemail_caller_display(message: VoicemailMessageRecord) -> str:
    """Anzeige ohne Caller directory: dieselbe Rückfallkette wie CallerIdentity.label()."""
    number = message.caller_number or ""
    identity = CallerIdentity(number, not number, None, None, None)
    return identity.label(fallback_name=message.raw_name)


class VoicemailListModel(TableModel):
    """Anrufbeantworter-Nachrichtenliste ("Anrufbeantworter"-Tab).

    Hebt neue (noch nicht gehörte) Nachrichten optisch hervor, direkt anhand des
    Box-eigenen is_new-Flags - anders als bei AllCallsListModel wird hier kein
    lokal verfolgtes last_seen_at gebraucht, die Box ist für "neu/gehört" allein
    massgeblich (siehe VoicemailRepository.insert_or_update)."""

    def __init__(self, messages: list[VoicemailMessageRecord] | None = None) -> None:
        # Anzeigenamen je Nachrichten-id (aus dem Caller directory, via set_messages);
        # ohne Eintrag fällt die Anzeige auf voicemail_caller_display zurück.
        self._labels: dict[int, str] = {}
        super().__init__(
            voicemail_columns(self.caller_label), messages, row_emphasis=lambda m: m.is_new
        )

    def set_messages(
        self, messages: list[VoicemailMessageRecord], labels: dict[int, str] | None = None
    ) -> None:
        self._labels = dict(labels or {})
        self._set_items(messages)

    def caller_label(self, message: VoicemailMessageRecord) -> str:
        return self._labels.get(message.id) or voicemail_caller_display(message)

    def message_at(self, row: int) -> VoicemailMessageRecord:
        return self._item_at(row)


class DataclassSortProxy(QSortFilterProxyModel):
    """Sortiert nach dem Sortierschlüssel der jeweiligen Column statt nach dem
    Anzeigetext (verhindert z.B. lexikographische Fehlsortierung bei 'm:ss'-Dauer
    oder Anrufzahlen). row_getter ist die bestehende contact_at()/call_at()-
    Methode des Quellmodells; *columns* dasselbe Column-Tupel wie im Modell."""

    def __init__(
        self,
        row_getter: Callable[[int], Any],
        columns: tuple[Column, ...],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._row_getter = row_getter
        self._columns = columns

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        column = self._columns[left.column()]
        a = column.key(self._row_getter(left.row()))
        b = column.key(self._row_getter(right.row()))
        if a is None:
            return True
        if b is None:
            return False
        return a < b


def configure_table(
    table: QTableView,
    proxy: QSortFilterProxyModel,
    selection_mode: QTableView.SelectionMode = QTableView.SelectionMode.SingleSelection,
) -> None:
    """Gemeinsame QTableView-Einrichtung aller Tabellen: Modell, Zeilenauswahl,
    gestreckte Spalten, keine vertikale Kopfzeile, nicht editierbar, 3-stufige
    Sortierung."""
    table.setModel(proxy)
    table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
    table.setSelectionMode(selection_mode)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    table.verticalHeader().setVisible(False)
    table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
    install_tristate_sorting(table, proxy)


def focus_search_if_supported(widget: QWidget) -> None:
    """Fokussiert das Suchfeld von *widget*, falls es eines hat (focus_search());
    Tabs ohne Suche (Anrufbeantworter) tun nichts."""
    focus = getattr(widget, "focus_search", None)
    if focus is not None:
        focus()


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


def focus_search_edit(search_edit: QLineEdit) -> None:
    """Fokussiert und markiert den Inhalt eines Suchfelds - gemeinsame focus_search()-
    Implementierung von ContactsView/AllCallsView/PhonebookView."""
    search_edit.setFocus()
    search_edit.selectAll()


def set_search_text_silently(search_edit: QLineEdit, search_timer: QTimer, text: str) -> None:
    """Übernimmt Suchtext von der jeweils anderen Ansicht, ohne textChanged auszulösen -
    sonst würden sich die Ansichten endlos gegenseitig zurückpropagieren (siehe
    CallsTab). Gemeinsame set_search_text()-Implementierung von ContactsView/
    AllCallsView. Kein sofortiges Reload: solange die Zielansicht nicht sichtbar ist,
    holt CallsTab das beim Umschalten nach, statt bei jedem Tastenanschlag der anderen
    Ansicht eine ungenutzte Query zu feuern."""
    if search_edit.text() == text:
        return
    search_edit.blockSignals(True)
    search_edit.setText(text)
    search_edit.blockSignals(False)
    search_timer.stop()


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


