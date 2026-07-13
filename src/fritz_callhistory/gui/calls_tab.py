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
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QStackedWidget, QStyle, QVBoxLayout, QWidget

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

        # Bewusst NICHT setCheckable(True): der native "checked"-Look bleibt
        # dauerhaft aktiv (sunken/hervorgehoben), nicht nur während des
        # Klicks selbst - das wirkt wie permanent gedrückt. Ein
        # QSS-Override dagegen bringt Checked/Unchecked zwar auf dieselbe
        # Boxgröße, macht dafür aber BEIDE Zustände dauerhaft flach/umrandet
        # statt des nativen, erhabenen Buttons wie bei den Nachbarbuttons
        # (Heute/Alle/...) - wirkt dann wieder wie permanent gedrückt, nur
        # in beiden Zuständen statt nur im aktiven. Deshalb stattdessen ein
        # gewöhnlicher (nicht anschaltbarer) Button, dessen "gedrückt"-Optik
        # rein transient beim tatsächlichen Klick erscheint; der
        # Gruppierungs-Status selbst wird in self._grouped gehalten und nur
        # über den Labeltext sichtbar gemacht (siehe _set_grouped).
        self._group_toggle = QPushButton("Gruppieren")
        self._group_toggle.clicked.connect(self._toggle_grouped)
        self._grouped = False

        self._stack = QStackedWidget()
        self._stack.addWidget(self.all_calls_view)
        self._stack.addWidget(self.contacts_view)

        # Anders als AllCallsView/GroupedContactsView (eigene Widgets mit
        # eigenem QVBoxLayout(self), die dadurch eine zweite, gestapelte
        # Standardmarge zum Fensterrand beitragen) ist toggle_row nur ein
        # verschachteltes QHBoxLayout ohne eigene Marge - ohne diese
        # Angleichung wirkt der Button dadurch weniger eingerückt als die
        # Such-/Filterzeile eine Ebene darunter.
        toggle_row = QHBoxLayout()
        left_margin = self.style().pixelMetric(QStyle.PixelMetric.PM_LayoutLeftMargin)
        toggle_row.setContentsMargins(left_margin, 0, 0, 0)
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
        # Beide Ansichten teilen sich einen Suchbegriff, obwohl sie eigene
        # QLineEdits haben (siehe deren "eigenständig testbar"-Docstrings) -
        # set_search_text() blockt die eigenen Signale beim Gegenstück, daher
        # keine Endlosschleife zwischen den beiden connect()-Aufrufen hier.
        self.all_calls_view.search_changed.connect(self.contacts_view.set_search_text)
        self.contacts_view.search_changed.connect(self.all_calls_view.set_search_text)

    @property
    def new_missed_calls_count(self) -> int:
        return self.all_calls_view.new_missed_calls_count

    def _toggle_grouped(self) -> None:
        self._set_grouped(not self._grouped)

    def _set_grouped(self, grouped: bool) -> None:
        self._grouped = grouped
        self._group_toggle.setText("Gruppierung aufheben" if grouped else "Gruppieren")
        self._stack.setCurrentIndex(_GROUPED_PAGE if grouped else _FLAT_PAGE)
        # Reload holt einen Suchtext nach, der eintraf, während diese Ansicht
        # verborgen war (set_search_text() selbst reloadet nicht, um bei
        # jedem Tastenanschlag in der jeweils anderen, sichtbaren Ansicht
        # keine ungenutzte Query auf der verborgenen zu feuern).
        if grouped:
            self.contacts_view.reload_contacts()
        else:
            self.all_calls_view.reload()

    def focus_search(self) -> None:
        self._stack.currentWidget().focus_search()

    def dial_selected(self) -> None:
        self._stack.currentWidget().dial_selected()

    def show_contact(self, contact_id: int) -> None:
        self._set_grouped(True)
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
