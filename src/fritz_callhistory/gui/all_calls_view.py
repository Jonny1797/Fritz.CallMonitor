"""Chronologische Anrufliste ueber alle Kontakte hinweg, mit Datumsfilter.

Ergaenzt die kontaktzentrierte Detailansicht (contact_detail.py) um eine
zeitraumbasierte Sicht, aehnlich der nativen Anrufliste der Fritz!Box.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import date, timedelta

from PySide6.QtCore import QDate, QModelIndex, Signal
from PySide6.QtWidgets import (
    QDateEdit,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from fritz_callhistory.db.repository import CallRepository
from fritz_callhistory.gui.models import AllCallsListModel

_ISO_DAY_START = "T00:00:00"
_ISO_DAY_END = "T23:59:59"


class AllCallsView(QWidget):
    contact_selected = Signal(int)

    def __init__(
        self,
        connection: sqlite3.Connection,
        today_provider: Callable[[], date] = date.today,
    ) -> None:
        super().__init__()
        self._calls_repo = CallRepository(connection)
        self._today_provider = today_provider
        self._filter_enabled = False

        today = QDate(self._today_provider())
        self._from_edit = QDateEdit(today)
        self._from_edit.setCalendarPopup(True)
        self._to_edit = QDateEdit(today)
        self._to_edit.setCalendarPopup(True)
        self._from_edit.dateChanged.connect(self._on_date_edited)
        self._to_edit.dateChanged.connect(self._on_date_edited)

        self._today_button = QPushButton("Heute")
        self._last_7_days_button = QPushButton("Letzte 7 Tage")
        self._this_month_button = QPushButton("Dieser Monat")
        self._all_button = QPushButton("Alle")
        self._today_button.clicked.connect(self._apply_preset_today)
        self._last_7_days_button.clicked.connect(self._apply_preset_last_7_days)
        self._this_month_button.clicked.connect(self._apply_preset_this_month)
        self._all_button.clicked.connect(self._apply_preset_all)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Von:"))
        filter_row.addWidget(self._from_edit)
        filter_row.addWidget(QLabel("Bis:"))
        filter_row.addWidget(self._to_edit)
        filter_row.addStretch()
        filter_row.addWidget(self._today_button)
        filter_row.addWidget(self._last_7_days_button)
        filter_row.addWidget(self._this_month_button)
        filter_row.addWidget(self._all_button)

        self._model = AllCallsListModel()
        self._table = QTableView()
        self._table.setModel(self._model)
        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self._table.clicked.connect(self._on_row_clicked)

        layout = QVBoxLayout(self)
        layout.addLayout(filter_row)
        layout.addWidget(self._table)

        self._reload()

    def _set_range(self, from_date: date, to_date: date) -> None:
        self._from_edit.blockSignals(True)
        self._to_edit.blockSignals(True)
        self._from_edit.setDate(QDate(from_date))
        self._to_edit.setDate(QDate(to_date))
        self._from_edit.blockSignals(False)
        self._to_edit.blockSignals(False)
        self._filter_enabled = True
        self._reload()

    def _apply_preset_today(self) -> None:
        today = self._today_provider()
        self._set_range(today, today)

    def _apply_preset_last_7_days(self) -> None:
        today = self._today_provider()
        self._set_range(today - timedelta(days=6), today)

    def _apply_preset_this_month(self) -> None:
        today = self._today_provider()
        self._set_range(today.replace(day=1), today)

    def _apply_preset_all(self) -> None:
        self._filter_enabled = False
        self._reload()

    def _on_date_edited(self, _value: QDate) -> None:
        self._filter_enabled = True
        self._reload()

    def reload(self) -> None:
        """Laedt die Liste unter Beibehaltung des aktuellen Filters neu (z.B. nach einem Sync)."""
        self._reload()

    def _reload(self) -> None:
        if self._filter_enabled:
            date_from = self._from_edit.date().toPython().isoformat() + _ISO_DAY_START
            date_to = self._to_edit.date().toPython().isoformat() + _ISO_DAY_END
        else:
            date_from = None
            date_to = None
        self._model.set_calls(self._calls_repo.all_calls(date_from=date_from, date_to=date_to))

    def _on_row_clicked(self, index: QModelIndex) -> None:
        call = self._model.call_at(index.row())
        self.contact_selected.emit(call.contact_id)
