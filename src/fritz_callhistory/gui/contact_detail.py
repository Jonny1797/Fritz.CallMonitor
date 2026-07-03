"""Detailansicht: Stammdaten und chronologische Anrufliste eines Kontakts."""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import QModelIndex, Signal
from PySide6.QtWidgets import QHeaderView, QLabel, QTableView, QVBoxLayout, QWidget

from fritz_callhistory.db.repository import CallRepository, Contact
from fritz_callhistory.gui.models import CallListModel

_NUMBER_COLUMN = 2


class ContactDetailWidget(QWidget):
    number_double_clicked = Signal(str)

    def __init__(self, connection: sqlite3.Connection) -> None:
        super().__init__()
        self._calls_repo = CallRepository(connection)

        self._title_label = QLabel()
        self._subtitle_label = QLabel()

        self._call_model = CallListModel()
        self._call_table = QTableView()
        self._call_table.setModel(self._call_model)
        self._call_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._call_table.verticalHeader().setVisible(False)
        self._call_table.setSelectionMode(QTableView.SelectionMode.NoSelection)
        self._call_table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self._call_table.doubleClicked.connect(self._on_call_table_double_clicked)

        layout = QVBoxLayout(self)
        layout.addWidget(self._title_label)
        layout.addWidget(self._subtitle_label)
        layout.addWidget(self._call_table)

        self.clear()

    def clear(self) -> None:
        self._title_label.setText("Kein Kontakt ausgewählt")
        self._subtitle_label.setText("")
        self._call_model.set_calls([])

    def show_contact(self, contact: Contact) -> None:
        name = (
            "Anonym / unterdrückt"
            if contact.is_anonymous
            else (contact.display_name or "Unbekannt")
        )
        self._title_label.setText(name)
        self._subtitle_label.setText(f"{contact.primary_number}  ·  {contact.call_count} Anrufe")
        self._call_model.set_calls(self._calls_repo.for_contact(contact.id))

    def _on_call_table_double_clicked(self, index: QModelIndex) -> None:
        if index.column() != _NUMBER_COLUMN:
            return
        call = self._call_model.call_at(index.row())
        number = call.called_number if call.call_type in (3, 11) else call.caller_number
        if number:
            self.number_double_clicked.emit(number)
