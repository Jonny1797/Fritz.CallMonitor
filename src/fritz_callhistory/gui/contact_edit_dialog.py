"""Dialog zum Anlegen/Bearbeiten eines lokalen Telefonbuch-Kontakts.

Unterstuetzt eine dynamische Anzahl Rufnummern pro Kontakt (Fritz!Fon/Box-
Telefonbuecher erlauben das ebenfalls). Persistiert nicht selbst - der
Aufrufer (gui/phonebook_view.py) entscheidet ueber create() vs. update().
"""

from __future__ import annotations

from functools import partial

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from fritz_callhistory.db.repository import LocalPhonebookContact
from fritz_callhistory.sync.normalize import normalize_number

_NUMBER_TYPES = ["home", "mobile", "work", "fax_work", "other"]
# Werte bleiben die internen Speicher-/Interop-Schluessel (DB, vCard/XML-Export
# in sync/phonebook_io.py) - nur die angezeigten Labels sind deutsch.
_NUMBER_TYPE_LABELS = {
    "home": "Privat",
    "mobile": "Mobil",
    "work": "Geschäftlich",
    "fax_work": "Fax (geschäftlich)",
    "other": "Sonstige",
}


class ContactEditDialog(QDialog):
    def __init__(
        self,
        existing: LocalPhonebookContact | None = None,
        prefill_number: str | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Kontakt bearbeiten" if existing else "Neuer Kontakt")
        self._existing = existing

        self._name_edit = QLineEdit(existing.display_name if existing else "")
        self._notes_edit = QTextEdit(existing.notes if existing and existing.notes else "")
        self._notes_edit.setFixedHeight(60)

        self._numbers_layout = QVBoxLayout()
        self._number_rows: list[tuple[QWidget, QLineEdit, QComboBox]] = []
        for number in (existing.numbers if existing else []):
            self._add_number_row(number.number_raw, number.number_type)
        if not self._number_rows:
            # prefill_number: Einstiegspunkt "Nummer aus Kontakte/Alle Anrufe
            # per Doppelklick zum Telefonbuch hinzufuegen" (gui/phonebook_view.py's
            # add_or_edit_number) - nur relevant, wenn noch kein bestehender
            # Kontakt geladen wurde (sonst kommen die Nummern schon von existing).
            self._add_number_row(prefill_number or "")

        add_number_button = QPushButton("+ Nummer hinzufügen")
        add_number_button.clicked.connect(lambda: self._add_number_row())

        form = QFormLayout()
        form.addRow("Name", self._name_edit)
        form.addRow("Nummern", self._numbers_layout)
        form.addRow("", add_number_button)
        form.addRow("Notizen", self._notes_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept_clicked)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _add_number_row(self, number_raw: str = "", number_type: str = "home") -> None:
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)

        number_edit = QLineEdit(number_raw)
        type_combo = QComboBox()
        for value in _NUMBER_TYPES:
            type_combo.addItem(_NUMBER_TYPE_LABELS[value], value)
        if number_type in _NUMBER_TYPES:
            type_combo.setCurrentIndex(type_combo.findData(number_type))
        remove_button = QPushButton("✕")
        remove_button.setFixedWidth(28)
        remove_button.clicked.connect(partial(self._remove_number_row, container))

        row.addWidget(number_edit)
        row.addWidget(type_combo)
        row.addWidget(remove_button)

        self._numbers_layout.addWidget(container)
        self._number_rows.append((container, number_edit, type_combo))

    def _remove_number_row(self, container: QWidget) -> None:
        # Ueber das Container-Widget selbst statt eines Zeilenindex entfernen,
        # da Indizes sich beim Entfernen anderer Zeilen zuvor verschieben
        # koennten (jede Zeile bindet ihren eigenen partial() auf sich selbst).
        self._number_rows = [row for row in self._number_rows if row[0] is not container]
        self._numbers_layout.removeWidget(container)
        container.deleteLater()

    def _on_accept_clicked(self) -> None:
        if not self._name_edit.text().strip():
            QMessageBox.warning(self, "Name fehlt", "Bitte einen Namen eingeben.")
            return
        if not self.contact_data()[2]:
            answer = QMessageBox.question(
                self,
                "Keine Nummer",
                "Dieser Kontakt hat keine Rufnummer. Trotzdem speichern?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.accept()

    def contact_data(self) -> tuple[str, str | None, list[tuple[str, str, str]]]:
        """(display_name, notes, [(number_raw, number_normalized, number_type), ...]).

        Numbers, die sich nach Normalisierung doppeln, werden entfernt (erste
        Eingabe gewinnt) - verhindert doppelte Zeilen fuer denselben Kontakt,
        wenn der Nutzer dieselbe Nummer versehentlich zweimal eintippt.
        """
        name = self._name_edit.text().strip()
        notes = self._notes_edit.toPlainText().strip() or None
        numbers: list[tuple[str, str, str]] = []
        seen_normalized: set[str] = set()
        for _container, number_edit, type_combo in self._number_rows:
            raw = number_edit.text().strip()
            if not raw:
                continue
            normalized, is_anonymous = normalize_number(raw)
            if is_anonymous or normalized in seen_normalized:
                continue
            seen_normalized.add(normalized)
            numbers.append((raw, normalized, type_combo.currentData()))
        return name, notes, numbers
