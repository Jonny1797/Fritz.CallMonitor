"""Detailansicht: Stammdaten und chronologische Anrufliste eines Kontakts."""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import QModelIndex, Signal
from PySide6.QtWidgets import QHeaderView, QLabel, QTableView, QVBoxLayout, QWidget

from fritz_callhistory.db.repository import CallRepository, Contact
from fritz_callhistory.gui.models import (
    CallListModel,
    DataclassSortProxy,
    call_number,
    contact_display_label,
    install_call_context_menu,
    install_tristate_sorting,
    port_device_display,
)
from fritz_callhistory.sync.normalize import ANONYMOUS_NUMBER

_NUMBER_COLUMN = 2


class ContactDetailWidget(QWidget):
    number_double_clicked = Signal(str)
    call_requested = Signal(str)

    def __init__(self, connection: sqlite3.Connection) -> None:
        super().__init__()
        self._calls_repo = CallRepository(connection)

        # Titel/Untertitel werden bewusst NICHT hier ins eigene Layout gehaengt:
        # main_window.py platziert sie stattdessen in einer eigenen, ueber die
        # gesamte Breite laufenden Kopfzeile OBERHALB des Splitters (statt nur
        # ueber der rechten Tabelle). Damit starten beide Tabellen exakt auf
        # derselben Hoehe und der Splitter (der beiden Kindern dieselbe
        # Gesamthoehe gibt) macht sie automatisch gleich hoch - ohne die
        # Kopfzeilenhoehe manuell nachbilden zu muessen (siehe vorherigen,
        # fragilen sizeHint()-Ansatz, der je nach Theme/Polish-Zeitpunkt leicht
        # danebenlag).
        self._title_label = QLabel()
        self._subtitle_label = QLabel()

        self._call_model = CallListModel()
        self._call_proxy = DataclassSortProxy(
            row_getter=self._call_model.call_at,
            key_fns={
                0: lambda c: c.call_date,
                1: lambda c: c.call_type,
                2: call_number,
                3: lambda c: c.duration_seconds,
                4: lambda c: port_device_display(c.device, c.port),
            },
        )
        self._call_proxy.setSourceModel(self._call_model)

        self._call_table = QTableView()
        self._call_table.setModel(self._call_proxy)
        self._call_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._call_table.verticalHeader().setVisible(False)
        self._call_table.setSelectionMode(QTableView.SelectionMode.NoSelection)
        self._call_table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self._call_table.doubleClicked.connect(self._on_call_table_double_clicked)
        install_tristate_sorting(self._call_table, self._call_proxy)
        install_call_context_menu(
            self._call_table, self._call_proxy, self._number_for_row, self.call_requested.emit
        )

        # Randlos: self._table (Kontakte links) haengt ohne umschliessendes
        # Layout direkt im Splitter und hat daher keine Aussenraender - ohne
        # Angleichung hier waere diese Tabelle sonst um die QVBoxLayout-
        # Standardraender kuerzer als die linke.
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._call_table)

        self.clear()

    @property
    def title_label(self) -> QLabel:
        """Fuer main_window.py, das Titel/Untertitel in eine eigene, ueber die
        gesamte Breite laufende Kopfzeile oberhalb des Splitters einhaengt
        (siehe Kommentar oben im Konstruktor)."""
        return self._title_label

    @property
    def subtitle_label(self) -> QLabel:
        return self._subtitle_label

    def clear(self) -> None:
        self._title_label.setText("Wählen Sie einen Kontakt aus, um mehr Details zu sehen.")
        self._subtitle_label.setText("")
        self._call_model.set_calls([])

    def show_contact(self, contact: Contact) -> None:
        name = contact_display_label(contact.is_anonymous, contact.display_name)
        self._title_label.setText(name)
        self._subtitle_label.setText(f"{contact.primary_number}  ·  {contact.call_count} Anrufe")
        self._call_model.set_calls(self._calls_repo.for_contact(contact.id))

    def _on_call_table_double_clicked(self, index: QModelIndex) -> None:
        if index.column() != _NUMBER_COLUMN:
            return
        source_row = self._call_proxy.mapToSource(index).row()
        call = self._call_model.call_at(source_row)
        number = call_number(call)
        if number:
            self.number_double_clicked.emit(number)

    def _number_for_row(self, row: int) -> str | None:
        number = call_number(self._call_model.call_at(row))
        return None if number == ANONYMOUS_NUMBER else number
