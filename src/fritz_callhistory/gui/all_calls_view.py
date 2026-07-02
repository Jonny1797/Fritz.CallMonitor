"""Chronologische Anrufliste ueber alle Kontakte hinweg, mit Datumsfilter.

Ergaenzt die kontaktzentrierte Detailansicht (contact_detail.py) um eine
zeitraumbasierte Sicht, aehnlich der nativen Anrufliste der Fritz!Box.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import date, datetime, timedelta

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

from fritz_callhistory.db.repository import CallRepository, SyncStateRepository
from fritz_callhistory.gui.models import AllCallsListModel

_ISO_DAY_START = "T00:00:00"
_ISO_DAY_END = "T23:59:59"
_MISSED_CALL_TYPE = 2
_LAST_SEEN_KEY = "missed_calls_last_seen_at"


class AllCallsView(QWidget):
    contact_selected = Signal(int)
    new_missed_calls_changed = Signal(int)

    def __init__(
        self,
        connection: sqlite3.Connection,
        today_provider: Callable[[], date] = date.today,
        now_provider: Callable[[], datetime] = datetime.now,
    ) -> None:
        super().__init__()
        self._calls_repo = CallRepository(connection)
        self._sync_state = SyncStateRepository(connection)
        self._today_provider = today_provider
        self._now_provider = now_provider
        self._filter_enabled = False
        self._new_missed_only = False
        self._new_missed_count = 0
        self._last_seen_at = self._load_or_init_last_seen_at()

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
        self._new_missed_button = QPushButton("Neu verpasst")
        self._today_button.clicked.connect(self._apply_preset_today)
        self._last_7_days_button.clicked.connect(self._apply_preset_last_7_days)
        self._this_month_button.clicked.connect(self._apply_preset_this_month)
        self._all_button.clicked.connect(self._apply_preset_all)
        self._new_missed_button.clicked.connect(self._apply_preset_new_missed)

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
        filter_row.addWidget(self._new_missed_button)

        # Eigene Zeile fuer "Als gesehen markieren": im Unterschied zu den
        # Presets oben (reine Sichtfilter) veraendert dieser Button
        # persistenten Zustand (last_seen_at in der DB) - bewusst visuell
        # abgesetzt, um Verwechslung mit einem reinen Filter-Klick zu vermeiden.
        self._new_missed_count_label = QLabel()
        self._mark_seen_button = QPushButton("Als gesehen markieren")
        self._mark_seen_button.clicked.connect(self._on_mark_seen_clicked)

        action_row = QHBoxLayout()
        action_row.addWidget(self._new_missed_count_label)
        action_row.addStretch()
        action_row.addWidget(self._mark_seen_button)

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
        layout.addLayout(action_row)
        layout.addWidget(self._table)

        self._reload()

    @property
    def new_missed_calls_count(self) -> int:
        return self._new_missed_count

    def _load_or_init_last_seen_at(self) -> str:
        value = self._sync_state.get(_LAST_SEEN_KEY)
        if value is None:
            # Erstlauf (keine bestehende Installation oder Update mit bereits
            # vorhandener Historie): nichts rueckwirkend als "neu" markieren.
            value = self._now_provider().isoformat()
            self._sync_state.set(_LAST_SEEN_KEY, value)
        return value

    def _set_range(self, from_date: date, to_date: date) -> None:
        self._new_missed_only = False
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
        self._new_missed_only = False
        self._filter_enabled = False
        self._reload()

    def _apply_preset_new_missed(self) -> None:
        self._filter_enabled = False
        self._new_missed_only = True
        self._reload()

    def _on_date_edited(self, _value: QDate) -> None:
        self._new_missed_only = False
        self._filter_enabled = True
        self._reload()

    def _on_mark_seen_clicked(self) -> None:
        self._last_seen_at = self._now_provider().isoformat()
        self._sync_state.set(_LAST_SEEN_KEY, self._last_seen_at)
        self._reload()

    def reload(self) -> None:
        """Laedt die Liste unter Beibehaltung des aktuellen Filters neu (z.B. nach einem Sync)."""
        self._reload()

    def _reload(self) -> None:
        if self._new_missed_only:
            calls = self._calls_repo.all_calls(
                date_from=self._last_seen_at, call_types=[_MISSED_CALL_TYPE]
            )
        elif self._filter_enabled:
            date_from = self._from_edit.date().toPython().isoformat() + _ISO_DAY_START
            date_to = self._to_edit.date().toPython().isoformat() + _ISO_DAY_END
            calls = self._calls_repo.all_calls(date_from=date_from, date_to=date_to)
        else:
            calls = self._calls_repo.all_calls()
        self._model.set_calls(calls)
        self._model.set_last_seen_at(self._last_seen_at)
        self._refresh_new_missed_count(precomputed=calls if self._new_missed_only else None)

    def _refresh_new_missed_count(self, precomputed: list | None = None) -> None:
        if precomputed is not None:
            count = len(precomputed)
        else:
            count = len(
                self._calls_repo.all_calls(
                    date_from=self._last_seen_at, call_types=[_MISSED_CALL_TYPE]
                )
            )
        self._new_missed_count = count
        self._new_missed_count_label.setText(f"{count} neu verpasst" if count else "")
        self.new_missed_calls_changed.emit(count)

    def _on_row_clicked(self, index: QModelIndex) -> None:
        call = self._model.call_at(index.row())
        self.contact_selected.emit(call.contact_id)
