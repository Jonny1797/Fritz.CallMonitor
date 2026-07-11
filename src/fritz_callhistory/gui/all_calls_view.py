"""Chronologische Anrufliste über alle Kontakte hinweg, mit Datumsfilter.

Ergänzt die kontaktzentrierte Detailansicht (contact_detail.py) um eine
zeitraumbasierte Sicht, ähnlich der nativen Anrufliste der Fritz!Box.
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
    QLineEdit,
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
    DataclassSortProxy,
    call_number,
    install_call_context_menu,
    install_debounced_search,
    install_tristate_sorting,
    port_device_display,
)
from fritz_callhistory.sync.normalize import normalize_number

_ISO_DAY_START = "T00:00:00"
_ISO_DAY_END = "T23:59:59"
_MISSED_CALL_TYPE = 2
_LAST_SEEN_KEY = "missed_calls_last_seen_at"
_NAME_NUMBER_COLUMN = 2
_LIVE_CALL_SENTINEL_ID = -1


@dataclass
class _LiveCall:
    caller_number: str
    called_number: str
    contact_id: int
    call_type: int  # LIVE_RINGING_CALL_TYPE oder LIVE_CONNECTED_CALL_TYPE
    started_at: str
    ended: bool = False  # Anruf beendet, wartet auf den nächsten erfolgreichen Sync (siehe on_live_disconnected)


class AllCallsView(QWidget):
    contact_selected = Signal(int)
    new_missed_calls_changed = Signal(int)
    live_call_ended = Signal()
    call_requested = Signal(str)
    search_changed = Signal(str)

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

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Suche nach Name oder Nummer …")
        self._search_timer = install_debounced_search(self._search_edit, self._reload)
        self._search_edit.textChanged.connect(self.search_changed.emit)

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

        # Eigene Zeile für "Als gesehen markieren": im Unterschied zu den
        # Presets oben (reine Sichtfilter) verändert dieser Button
        # persistenten Zustand (last_seen_at in der DB) - bewusst visuell
        # abgesetzt, um Verwechslung mit einem reinen Filter-Klick zu vermeiden.
        self._new_missed_count_label = QLabel()
        self._mark_seen_button = QPushButton("Als gesehen markieren")
        self._mark_seen_button.setToolTip("Alle neu verpassten Anrufe als gesehen markieren")
        self._mark_seen_button.clicked.connect(self._on_mark_seen_clicked)

        action_row = QHBoxLayout()
        action_row.addWidget(self._new_missed_count_label)
        action_row.addStretch()
        action_row.addWidget(self._mark_seen_button)

        self._model = AllCallsListModel()
        self._proxy = DataclassSortProxy(
            row_getter=self._model.call_at,
            key_fns={
                0: lambda c: c.call_date,
                1: lambda c: c.call_type,
                2: lambda c: (c.contact_display_name or c.contact_primary_number or "").lower(),
                3: lambda c: c.duration_seconds,
                4: lambda c: port_device_display(c.device, c.port),
            },
        )
        self._proxy.setSourceModel(self._model)

        self._table = QTableView()
        self._table.setModel(self._proxy)
        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self._table.doubleClicked.connect(self._on_row_double_clicked)
        install_tristate_sorting(self._table, self._proxy)
        install_call_context_menu(
            self._table, self._proxy, self._number_for_row, self.call_requested.emit
        )

        layout = QVBoxLayout(self)
        layout.addWidget(self._search_edit)
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
            # vorhandener Historie): nichts rückwirkend als "neu" markieren.
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
        """Lädt die Liste unter Beibehaltung des aktuellen Filters neu (z.B. nach einem Sync)."""
        self._reload()

    def set_search_text(self, text: str) -> None:
        """Übernimmt Suchtext von der jeweils anderen Ansicht (siehe CallsTab),
        ohne search_changed erneut auszulösen - sonst würde jede Ansicht die
        andere endlos zurück-propagieren. Kein sofortiges _reload(): solange
        diese Ansicht nicht sichtbar ist, holt CallsTab._set_grouped() das beim
        Umschalten nach, statt bei jedem Tastenanschlag der anderen Ansicht
        eine ungenutzte Query zu feuern."""
        if self._search_edit.text() == text:
            return
        self._search_edit.blockSignals(True)
        self._search_edit.setText(text)
        self._search_edit.blockSignals(False)
        self._search_timer.stop()

    def _reload(self) -> None:
        search = self._search_edit.text()
        if self._new_missed_only:
            calls = self._calls_repo.all_calls(
                date_from=self._last_seen_at, call_types=[_MISSED_CALL_TYPE], search=search
            )
        elif self._filter_enabled:
            date_from = self._from_edit.date().toPython().isoformat() + _ISO_DAY_START
            date_to = self._to_edit.date().toPython().isoformat() + _ISO_DAY_END
            calls = self._calls_repo.all_calls(date_from=date_from, date_to=date_to, search=search)
        else:
            calls = self._calls_repo.all_calls(search=search)

        if not self._new_missed_only:
            # Live-Anrufe (klingelt/verbunden) immer oben zeigen, ausser im
            # "Neu verpasst"-Preset - der ist semantisch nur für bereits
            # abgeschlossene, verpasste Anrufe gedacht.
            calls = self._live_calls_as_call_with_contact(search) + calls

        self._model.set_calls(calls)
        self._model.set_last_seen_at(self._last_seen_at)
        # precomputed nur ohne aktive Suche verwenden: die globale "neu
        # verpasst"-Badge (new_missed_calls_changed) und der "als gesehen
        # markieren"-Button sollen sich nicht mit der Trefferzahl der Suche
        # verändern, sondern nur die tatsächliche Anzahl ungesehener Anrufe
        # widerspiegeln - _refresh_new_missed_count() rechnet sonst ohnehin
        # separat (ungefiltert) nach.
        self._refresh_new_missed_count(
            precomputed=calls if (self._new_missed_only and not search) else None
        )

    def _live_calls_as_call_with_contact(self, search: str = "") -> list[CallWithContact]:
        query = search.lower()
        result = []
        for live in sorted(self._live_calls.values(), key=lambda c: c.started_at, reverse=True):
            contact = self._contacts_repo.get(live.contact_id)
            display_name = contact.display_name if contact else None
            primary_number = contact.primary_number if contact else live.caller_number
            if (
                query
                and query not in (display_name or "").lower()
                and query not in (primary_number or "").lower()
            ):
                continue
            result.append(
                CallWithContact(
                    id=_LIVE_CALL_SENTINEL_ID,  # Sentinel: kein echter DB-Eintrag, nur zur Anzeige
                    contact_id=live.contact_id,
                    # Beendete Anrufe werden generisch als "Eingehend" dargestellt,
                    # statt sofort zu verschwinden - CallMonitor verfolgt ohnehin
                    # ausschliesslich eingehende RING-Ereignisse (siehe
                    # fritz/callmonitor.py's parse_event), daher immer korrekt.
                    call_type=1 if live.ended else live.call_type,
                    caller_number=live.caller_number,
                    called_number=live.called_number,
                    port=None,
                    device=None,
                    call_date=live.started_at,
                    duration_seconds=None,
                    raw_name=None,
                    contact_display_name=display_name,
                    contact_primary_number=primary_number,
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
        # Der Eintrag wird nicht sofort entfernt, sondern nur als beendet
        # markiert (siehe _live_calls_as_call_with_contact) - so bleibt die
        # Zeile sichtbar, bis der dadurch ausgelöste Sync (live_call_ended
        # -> MainWindow._trigger_sync) den echten Eintrag gebracht hat, statt
        # kurz zu verschwinden und dann wieder aufzutauchen.
        live = self._live_calls.get(connection_id)
        if live is not None:
            live.ended = True
            self._reload()
            self.live_call_ended.emit()

    def clear_ended_live_calls(self) -> None:
        """Entfernt beendete Live-Anrufe, nachdem der dadurch ausgelöste Sync
        abgeschlossen ist (siehe MainWindow._on_sync_finished) - der echte,
        jetzt synchronisierte Eintrag ersetzt die Platzhalterzeile dann nahtlos."""
        ended_ids = [cid for cid, live in self._live_calls.items() if live.ended]
        for connection_id in ended_ids:
            del self._live_calls[connection_id]

    def clear_live_calls(self) -> None:
        """Verwirft alle laufend verfolgten Anrufe, z.B. wenn die CallMonitor-
        Verbindung abbricht und ihr Zustand nicht mehr vertrauenswürdig ist."""
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
        self._mark_seen_button.setEnabled(count > 0)
        self.new_missed_calls_changed.emit(count)

    def _on_row_double_clicked(self, index: QModelIndex) -> None:
        if index.column() != _NAME_NUMBER_COLUMN:
            return
        source_row = self._proxy.mapToSource(index).row()
        call = self._model.call_at(source_row)
        self.contact_selected.emit(call.contact_id)

    def _number_for_row(self, row: int) -> str | None:
        call = self._model.call_at(row)
        if call.id == _LIVE_CALL_SENTINEL_ID or call.contact_is_anonymous:
            return None
        return call_number(call)
