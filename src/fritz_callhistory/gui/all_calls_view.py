"""Chronologische Anrufliste ueber alle Kontakte hinweg, mit Datumsfilter.

Ergaenzt die kontaktzentrierte Detailansicht (contact_detail.py) um eine
zeitraumbasierte Sicht, aehnlich der nativen Anrufliste der Fritz!Box.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
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

from fritz_callhistory.db.repository import (
    CallRepository,
    CallWithContact,
    ContactRepository,
    SyncStateRepository,
)
from fritz_callhistory.gui.models import (
    LIVE_CONNECTED_CALL_TYPE,
    LIVE_RINGING_CALL_TYPE,
    AllCallsListModel,
)
from fritz_callhistory.sync.normalize import normalize_number

_ISO_DAY_START = "T00:00:00"
_ISO_DAY_END = "T23:59:59"
_MISSED_CALL_TYPE = 2
_LAST_SEEN_KEY = "missed_calls_last_seen_at"
_NAME_NUMBER_COLUMN = 2


@dataclass
class _LiveCall:
    caller_number: str
    called_number: str
    contact_id: int
    call_type: int  # LIVE_RINGING_CALL_TYPE oder LIVE_CONNECTED_CALL_TYPE
    started_at: str


class AllCallsView(QWidget):
    contact_selected = Signal(int)
    new_missed_calls_changed = Signal(int)
    live_call_ended = Signal()
    number_double_clicked = Signal(str)

    def __init__(
        self,
        connection: sqlite3.Connection,
        today_provider: Callable[[], date] = date.today,
        now_provider: Callable[[], datetime] = datetime.now,
    ) -> None:
        super().__init__()
        self._calls_repo = CallRepository(connection)
        self._contacts_repo = ContactRepository(connection)
        self._sync_state = SyncStateRepository(connection)
        self._today_provider = today_provider
        self._now_provider = now_provider
        self._filter_enabled = False
        self._new_missed_only = False
        self._new_missed_count = 0
        self._last_seen_at = self._load_or_init_last_seen_at()
        self._live_calls: dict[str, _LiveCall] = {}

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
        self._table.doubleClicked.connect(self._on_row_double_clicked)

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

        if not self._new_missed_only:
            # Live-Anrufe (klingelt/verbunden) immer oben zeigen, ausser im
            # "Neu verpasst"-Preset - der ist semantisch nur fuer bereits
            # abgeschlossene, verpasste Anrufe gedacht.
            calls = self._live_calls_as_call_with_contact() + calls

        self._model.set_calls(calls)
        self._model.set_last_seen_at(self._last_seen_at)
        self._refresh_new_missed_count(precomputed=calls if self._new_missed_only else None)

    def _live_calls_as_call_with_contact(self) -> list[CallWithContact]:
        result = []
        for live in sorted(self._live_calls.values(), key=lambda c: c.started_at, reverse=True):
            contact = self._contacts_repo.get(live.contact_id)
            result.append(
                CallWithContact(
                    id=-1,  # Sentinel: kein echter DB-Eintrag, nur zur Anzeige
                    contact_id=live.contact_id,
                    call_type=live.call_type,
                    caller_number=live.caller_number,
                    called_number=live.called_number,
                    port=None,
                    device=None,
                    call_date=live.started_at,
                    duration_seconds=None,
                    raw_name=None,
                    contact_display_name=contact.display_name if contact else None,
                    contact_primary_number=(
                        contact.primary_number if contact else live.caller_number
                    ),
                    contact_is_anonymous=contact.is_anonymous if contact else False,
                )
            )
        return result

    def on_live_ring(self, connection_id: str, caller_number: str, called_number: str) -> None:
        normalized, is_anonymous = normalize_number(caller_number)
        contact_id = self._contacts_repo.upsert(normalized, is_anonymous=is_anonymous)
        self._live_calls[connection_id] = _LiveCall(
            caller_number=caller_number,
            called_number=called_number,
            contact_id=contact_id,
            call_type=LIVE_RINGING_CALL_TYPE,
            started_at=self._now_provider().isoformat(),
        )
        self._reload()

    def on_live_connected(self, connection_id: str) -> None:
        live = self._live_calls.get(connection_id)
        if live is not None:
            live.call_type = LIVE_CONNECTED_CALL_TYPE
            self._reload()

    def on_live_disconnected(self, connection_id: str) -> None:
        if self._live_calls.pop(connection_id, None) is not None:
            self._reload()
            self.live_call_ended.emit()

    def clear_live_calls(self) -> None:
        """Verwirft alle laufend verfolgten Anrufe, z.B. wenn die CallMonitor-
        Verbindung abbricht und ihr Zustand nicht mehr vertrauenswuerdig ist."""
        if self._live_calls:
            self._live_calls.clear()
            self._reload()

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

    def _on_row_double_clicked(self, index: QModelIndex) -> None:
        if index.column() != _NAME_NUMBER_COLUMN:
            return
        call = self._model.call_at(index.row())
        if call.contact_is_anonymous:
            return
        self.number_double_clicked.emit(call.contact_primary_number)
