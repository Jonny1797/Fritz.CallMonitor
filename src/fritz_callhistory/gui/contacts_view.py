"""Kontaktliste (nach Nummer gruppierte Anrufe), Suche und Detailansicht.

Fasst jede Nummer, die je in calls aufgetaucht ist, zu einem Kontakt zusammen
(siehe ContactRepository) und zeigt daneben die volle Anrufhistorie des
ausgewählten Kontakts (contact_detail.py). Eingebettet als "gruppierter" Modus
von gui/calls_tab.py's CallsTab - eigenständig gehalten (kennt weder
CallsTab noch MainWindow), damit es wie AllCallsView/PhonebookTab/VoicemailView
für sich testbar bleibt.
"""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from fritz_callhistory.db.repository import ContactRepository
from fritz_callhistory.gui.contact_detail import ContactDetailWidget
from fritz_callhistory.gui.models import (
    ContactListModel,
    DataclassSortProxy,
    install_call_context_menu,
    install_debounced_search,
    install_tristate_sorting,
    selected_source_row,
)

_CONTACT_NAME_COLUMN = 0


class GroupedContactsView(QWidget):
    call_requested = Signal(str)
    number_double_clicked = Signal(str)
    search_changed = Signal(str)

    def __init__(self, connection: sqlite3.Connection) -> None:
        super().__init__()
        self._contacts_repo = ContactRepository(connection)
        self._contact_model = ContactListModel()

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Suche nach Name oder Nummer …")
        self._search_timer = install_debounced_search(self._search_edit, self.reload_contacts)
        self._search_edit.textChanged.connect(self.search_changed.emit)

        self._contact_proxy = DataclassSortProxy(
            row_getter=self._contact_model.contact_at,
            key_fns={
                0: lambda c: (c.display_name or "").lower(),
                1: lambda c: c.last_call_date,
                2: lambda c: c.call_count,
            },
        )
        self._contact_proxy.setSourceModel(self._contact_model)

        self._table = QTableView()
        self._table.setModel(self._contact_proxy)
        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.selectionModel().selectionChanged.connect(self._on_selection_changed)
        self._table.doubleClicked.connect(self._on_contact_table_double_clicked)
        install_tristate_sorting(self._table, self._contact_proxy)
        install_call_context_menu(
            self._table, self._contact_proxy, self._contact_number_for_row, self.call_requested.emit
        )

        self._detail = ContactDetailWidget(connection)
        self._contact_model.modelReset.connect(self._detail.clear)
        self._detail.call_requested.connect(self.call_requested.emit)
        self._detail.number_double_clicked.connect(self.number_double_clicked.emit)

        # Titel/Untertitel des ausgewählten Kontakts laufen über die gesamte
        # Breite OBERHALB des Splitters, statt (wie früher) nur über der
        # rechten Anrufliste zu stehen - sonst wäre die linke Kontaktliste um
        # genau diese Kopfzeilenhöhe kürzer als die rechte Tabelle (der
        # Splitter gibt beiden Kindern dieselbe Gesamthöhe, aber nur die
        # rechte Seite hätte intern eine Kopfzeile). So haben beide Splitter-
        # Kinder von Anfang an nur eine Tabelle als Inhalt und werden dadurch
        # automatisch gleich hoch.
        detail_header_row = QHBoxLayout()
        detail_header_row.addWidget(self._detail.title_label)
        detail_header_row.addWidget(self._detail.subtitle_label)
        detail_header_row.addStretch()

        splitter = QSplitter()
        splitter.addWidget(self._table)
        splitter.addWidget(self._detail)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        layout = QVBoxLayout(self)
        layout.addWidget(self._search_edit)
        layout.addLayout(detail_header_row)
        # stretch=1: ohne das teilt Qt den übrigen vertikalen Platz zwischen
        # der Kopfzeile (QLabels sind per Default "Preferred", also wachstums-
        # fähig, nicht nur der Splitter) etwa hälftig auf - der Splitter soll
        # aber den gesamten Platz bekommen, die Kopfzeile nur ihre Zeilenhöhe.
        layout.addWidget(splitter, 1)

        self.reload_contacts()

    def reload_contacts(self) -> None:
        self._contact_model.set_contacts(self._contacts_repo.search(self._search_edit.text()))

    def set_search_text(self, text: str) -> None:
        """Übernimmt Suchtext von der jeweils anderen Ansicht (siehe CallsTab),
        ohne search_changed erneut auszulösen - sonst würde jede Ansicht die
        andere endlos zurück-propagieren. Kein sofortiges reload_contacts():
        solange diese Ansicht nicht sichtbar ist, holt CallsTab._set_grouped()
        das beim Umschalten nach, statt bei jedem Tastenanschlag der anderen
        Ansicht eine ungenutzte Query zu feuern."""
        if self._search_edit.text() == text:
            return
        self._search_edit.blockSignals(True)
        self._search_edit.setText(text)
        self._search_edit.blockSignals(False)
        self._search_timer.stop()

    def show_contact(self, contact_id: int) -> None:
        # search_timer.stop() ist nötig: search_edit.clear() löst über
        # textChanged sonst den 250ms-Debounce-Timer aus, der 250ms später
        # einen zweiten, überflüssigen reload_contacts() feuern würde -
        # dessen modelReset räumt über die bestehende Verbindung die gerade
        # frisch angezeigte Detailansicht wieder leer.
        self._search_edit.clear()
        self._search_timer.stop()
        self.reload_contacts()
        source_row = self._contact_model.index_of(contact_id)
        if source_row is not None:
            proxy_row = self._contact_proxy.mapFromSource(self._contact_model.index(source_row, 0)).row()
            self._table.selectRow(proxy_row)

    def _on_contact_table_double_clicked(self, index) -> None:
        if index.column() != _CONTACT_NAME_COLUMN:
            return
        source_row = self._contact_proxy.mapToSource(index).row()
        contact = self._contact_model.contact_at(source_row)
        if contact.is_anonymous:
            return
        self.number_double_clicked.emit(contact.primary_number)

    def _contact_number_for_row(self, row: int) -> str | None:
        contact = self._contact_model.contact_at(row)
        return None if contact.is_anonymous else contact.primary_number

    def focus_search(self) -> None:
        self._search_edit.setFocus()
        self._search_edit.selectAll()

    def dial_selected(self) -> None:
        row = selected_source_row(self._table, self._contact_proxy)
        if row is None:
            return
        number = self._contact_number_for_row(row)
        if number is not None:
            self.call_requested.emit(number)

    def _on_selection_changed(self, selected, deselected) -> None:
        indexes = selected.indexes()
        if not indexes:
            self._detail.clear()
            return
        source_row = self._contact_proxy.mapToSource(indexes[0]).row()
        contact = self._contact_model.contact_at(source_row)
        self._detail.show_contact(contact)
