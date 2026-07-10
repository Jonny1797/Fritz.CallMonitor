"""Einstellungsdialog: Sync-Intervall, Telefonbuch-Auswahl, Anruf-Benachrichtigung.

Schreibt Änderungen nur in die Config-TOML (siehe save()) - für ihre Wirkung ist
ein Neustart der App nötig, da Sync-Intervall/Telefonbuch-IDs aktuell nur einmalig
beim Start in main_window.py/app.py in Worker-Closures bzw. den Auto-Sync-Timer
eingebrannt werden (keine Laufzeit-Neukonfiguration vorhanden).

Kennt bewusst weder FritzBoxClient noch Worker-Threads: MainWindow holt die
Telefonbuchliste selbst (PhonebookListWorker, an MainWindow statt an diesen
Dialog gehängt - siehe _open_settings_dialog()) und reicht das Ergebnis über
set_phonebooks()/set_phonebooks_unavailable() synchron herein.
"""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)

from fritz_callhistory import config as config_module
from fritz_callhistory.config import Config

_MIN_SYNC_INTERVAL_MINUTES = 1
_MAX_SYNC_INTERVAL_MINUTES = 1440


class SettingsDialog(QDialog):
    def __init__(self, config: Config, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Einstellungen")

        self._phonebooks_loaded = False
        self._phonebook_checkboxes: list[tuple[int, QCheckBox]] = []
        self._existing_phonebook_ids = set(config.phonebook_ids)

        self._interval_spin = QSpinBox()
        self._interval_spin.setRange(_MIN_SYNC_INTERVAL_MINUTES, _MAX_SYNC_INTERVAL_MINUTES)
        self._interval_spin.setSuffix(" Minuten")
        self._interval_spin.setValue(config.sync_interval_minutes)

        self._popup_checkbox = QCheckBox("Bei eingehenden Anrufen benachrichtigen")
        self._popup_checkbox.setChecked(config.show_incoming_call_popup)

        self._all_phonebooks_checkbox = QCheckBox("Alle Telefonbücher einbeziehen")
        self._all_phonebooks_checkbox.setChecked(not config.phonebook_ids)
        self._all_phonebooks_checkbox.toggled.connect(self._on_all_phonebooks_toggled)

        self._phonebook_list_layout = QVBoxLayout()
        self._phonebook_status_label = QLabel("Lade Telefonbücher …")
        self._phonebook_list_layout.addWidget(self._phonebook_status_label)

        phonebook_box = QGroupBox("Telefonbücher")
        phonebook_layout = QVBoxLayout(phonebook_box)
        phonebook_layout.addWidget(self._all_phonebooks_checkbox)
        phonebook_layout.addLayout(self._phonebook_list_layout)

        form = QFormLayout()
        form.addRow("Sync-Intervall", self._interval_spin)
        form.addRow(self._popup_checkbox)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(phonebook_box)
        layout.addWidget(buttons)

        self._on_all_phonebooks_toggled(self._all_phonebooks_checkbox.isChecked())

    def _on_all_phonebooks_toggled(self, checked: bool) -> None:
        for _pid, checkbox in self._phonebook_checkboxes:
            checkbox.setEnabled(not checked)

    def set_phonebooks(self, phonebooks: list[tuple[int, str]]) -> None:
        """Baut die Checkbox-Liste auf; checked, wenn die id in config.phonebook_ids
        war (oder alle, wenn phonebook_ids leer war - siehe resolved_phonebook_ids())."""
        self._phonebook_status_label.hide()
        for pid, name in phonebooks:
            checkbox = QCheckBox(f"{name} ({pid})")
            checkbox.setChecked(pid in self._existing_phonebook_ids)
            checkbox.setEnabled(not self._all_phonebooks_checkbox.isChecked())
            self._phonebook_list_layout.addWidget(checkbox)
            self._phonebook_checkboxes.append((pid, checkbox))
        self._phonebooks_loaded = True

    def set_phonebooks_unavailable(self, message: str) -> None:
        """Kein list_phonebooks_fn (keine Zugangsdaten) oder Ladefehler - Picker bleibt
        deaktiviert, phonebook_ids wird beim Speichern unverändert übernommen."""
        self._phonebook_status_label.setText(message)
        self._all_phonebooks_checkbox.setEnabled(False)

    def save(self, base: Config) -> Config:
        phonebook_ids = base.phonebook_ids
        if self._phonebooks_loaded:
            phonebook_ids = (
                []
                if self._all_phonebooks_checkbox.isChecked()
                else [pid for pid, checkbox in self._phonebook_checkboxes if checkbox.isChecked()]
            )
        new_config = replace(
            base,
            sync_interval_minutes=self._interval_spin.value(),
            show_incoming_call_popup=self._popup_checkbox.isChecked(),
            phonebook_ids=phonebook_ids,
        )
        config_module.save(new_config)
        return new_config
