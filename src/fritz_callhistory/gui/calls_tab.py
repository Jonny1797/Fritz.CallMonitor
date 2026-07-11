"""Vereint AllCallsView (flache, chronologische Liste) und GroupedContactsView
(nach Nummer gruppiert, mit Suche + Detailansicht) hinter einem "Gruppieren"-
Umschalter - beides sind Sichten auf dieselben calls-Zeilen (siehe
contacts_view.py's Docstring), daher genügt ein QStackedWidget statt zweier
getrennter Tabs."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import date, datetime

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from fritz_callhistory.gui.all_calls_view import AllCallsView
from fritz_callhistory.gui.contacts_view import GroupedContactsView

_FLAT_PAGE = 0
_GROUPED_PAGE = 1


class CallsTab(QWidget):
    call_requested = Signal(str)
    number_double_clicked = Signal(str)
    new_missed_calls_changed = Signal(int)
    live_call_ended = Signal()

    def __init__(
        self,
        connection: sqlite3.Connection,
        today_provider: Callable[[], date] = date.today,
        now_provider: Callable[[], datetime] = datetime.now,
    ) -> None:
        super().__init__()
        self.all_calls_view = AllCallsView(
            connection, today_provider=today_provider, now_provider=now_provider
        )
        self.contacts_view = GroupedContactsView(connection)

        self._group_toggle = QPushButton("Gruppieren")
        self._group_toggle.setCheckable(True)
        self._group_toggle.toggled.connect(self._on_group_toggled)

        self._stack = QStackedWidget()
        self._stack.addWidget(self.all_calls_view)
        self._stack.addWidget(self.contacts_view)

        toggle_row = QHBoxLayout()
        toggle_row.addWidget(self._group_toggle)
        toggle_row.addStretch()

        layout = QVBoxLayout(self)
        layout.addLayout(toggle_row)
        layout.addWidget(self._stack)

        self.all_calls_view.contact_selected.connect(self.show_contact)
        self.all_calls_view.call_requested.connect(self.call_requested.emit)
        self.all_calls_view.new_missed_calls_changed.connect(self.new_missed_calls_changed.emit)
        self.all_calls_view.live_call_ended.connect(self.live_call_ended.emit)
        self.contacts_view.call_requested.connect(self.call_requested.emit)
        self.contacts_view.number_double_clicked.connect(self.number_double_clicked.emit)

    @property
    def new_missed_calls_count(self) -> int:
        return self.all_calls_view.new_missed_calls_count

    def _on_group_toggled(self, checked: bool) -> None:
        self._stack.setCurrentIndex(_GROUPED_PAGE if checked else _FLAT_PAGE)
        if checked:
            self.contacts_view.reload_contacts()

    def show_contact(self, contact_id: int) -> None:
        self._group_toggle.setChecked(True)
        self.contacts_view.show_contact(contact_id)

    def reload_contacts(self) -> None:
        self.contacts_view.reload_contacts()

    def reload(self) -> None:
        self.all_calls_view.reload()

    def on_live_ring(self, connection_id: str, caller_number: str, called_number: str) -> None:
        self.all_calls_view.on_live_ring(connection_id, caller_number, called_number)

    def on_live_connected(self, connection_id: str) -> None:
        self.all_calls_view.on_live_connected(connection_id)

    def on_live_disconnected(self, connection_id: str) -> None:
        self.all_calls_view.on_live_disconnected(connection_id)

    def clear_ended_live_calls(self) -> None:
        self.all_calls_view.clear_ended_live_calls()

    def clear_live_calls(self) -> None:
        self.all_calls_view.clear_live_calls()
