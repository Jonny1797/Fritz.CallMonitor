"""Telefonbuch-Auswahl für "Von Box importieren…": fragt bei jedem Klick live ab,
welche Telefonbücher gerade auf der Box existieren, statt (wie zuvor) die
Einstellungen-Auswahl mitzubenutzen, die nur die Namensauflösung im Hintergrund
steuert (siehe settings_dialog.py).

Kennt bewusst weder FritzBoxClient noch Worker-Threads - MainWindow holt die
Telefonbuchliste selbst (PhonebookListWorker) und reicht das Ergebnis über
set_phonebooks()/set_phonebooks_unavailable() synchron herein (siehe
_open_phonebook_import_dialog()). Anders als SettingsDialog gibt es hier keinen
manuellen ID-Fallback: ohne Box-Verbindung lässt sich ohnehin nichts importieren,
daher bleibt OK deaktiviert, bis eine echte Telefonbuchliste eintrifft.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
)


class PhonebookPickerDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Von Box importieren")

        self._phonebook_checkboxes: list[tuple[int, QCheckBox]] = []

        self._explanation_label = QLabel(
            "Kontakte aus den ausgewählten Telefonbüchern der Box werden "
            "importiert bzw. mit bereits importierten Kontakten abgeglichen "
            "(per eindeutiger Box-Id). Rein lokal angelegte Kontakte werden nur "
            "dann automatisch verknüpft, wenn ihre Rufnummern exakt mit einem "
            "Box-Eintrag übereinstimmen - andernfalls können Duplikate entstehen."
        )
        self._explanation_label.setWordWrap(True)

        self._status_label = QLabel("Lade Telefonbücher …")

        self._error_label = QLabel("")
        self._error_label.setWordWrap(True)
        self._error_label.setStyleSheet("color: red;")
        self._error_label.setVisible(False)

        self._checkbox_layout = QVBoxLayout()
        self._checkbox_layout.addWidget(self._status_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self._ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._ok_button.setEnabled(False)

        layout = QVBoxLayout(self)
        layout.addWidget(self._explanation_label)
        layout.addLayout(self._checkbox_layout)
        layout.addWidget(self._error_label)
        layout.addWidget(buttons)

    def set_phonebooks(self, phonebooks: list[tuple[int, str]]) -> None:
        """Baut die Checkbox-Liste auf, alle vorbelegt - der Nutzer schränkt bei
        Bedarf gezielt für diesen einen Import-Lauf ein."""
        self._status_label.hide()
        for pid, name in phonebooks:
            checkbox = QCheckBox(f"{name} ({pid})")
            checkbox.setChecked(True)
            self._checkbox_layout.addWidget(checkbox)
            self._phonebook_checkboxes.append((pid, checkbox))
        self._ok_button.setEnabled(True)

    def set_phonebooks_unavailable(self, message: str) -> None:
        """Kein list_phonebooks_fn (keine Zugangsdaten) oder Ladefehler - ohne
        Box-Verbindung gibt es nichts auszuwählen, OK bleibt deaktiviert und nur
        Abbrechen führt weiter."""
        self._status_label.setText(message)

    def selected_phonebook_ids(self) -> list[int]:
        return [pid for pid, checkbox in self._phonebook_checkboxes if checkbox.isChecked()]

    def accept(self) -> None:
        if not self.selected_phonebook_ids():
            self._error_label.setText("Bitte mindestens ein Telefonbuch auswählen.")
            self._error_label.setVisible(True)
            return
        self._error_label.setVisible(False)
        super().accept()
