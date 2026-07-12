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
    QLineEdit,
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
        self._manual_entry_active = False
        self._parsed_manual_ids: list[int] = []
        self._phonebook_checkboxes: list[tuple[int, QCheckBox]] = []
        self._existing_phonebook_ids = set(config.phonebook_ids)

        self._interval_spin = QSpinBox()
        self._interval_spin.setRange(_MIN_SYNC_INTERVAL_MINUTES, _MAX_SYNC_INTERVAL_MINUTES)
        self._interval_spin.setSuffix(" Minuten")
        self._interval_spin.setValue(config.sync_interval_minutes)

        self._popup_checkbox = QCheckBox("Bei eingehenden Anrufen benachrichtigen")
        self._popup_checkbox.setChecked(config.show_incoming_call_popup)

        self._minimize_to_tray_checkbox = QCheckBox(
            "Beim Schliessen in den Infobereich (Tray) minimieren, statt die App zu beenden"
        )
        self._minimize_to_tray_checkbox.setChecked(config.minimize_to_tray_on_close)

        self._phonebook_explanation_label = QLabel(
            "Legt fest, welche Telefonbücher der Box für die Namensauflösung "
            "(Hintergrund-Abgleich) verwendet werden. 'Von Box importieren…' im "
            "Telefonbuch-Menü fragt bei jedem Import separat nach."
        )
        self._phonebook_explanation_label.setWordWrap(True)

        self._all_phonebooks_checkbox = QCheckBox("Alle Telefonbücher einbeziehen")
        self._all_phonebooks_checkbox.setChecked(not config.phonebook_ids)
        self._all_phonebooks_checkbox.toggled.connect(self._on_all_phonebooks_toggled)

        self._phonebook_list_layout = QVBoxLayout()
        self._phonebook_status_label = QLabel("Lade Telefonbücher …")
        self._phonebook_list_layout.addWidget(self._phonebook_status_label)

        self._manual_ids_edit = QLineEdit()
        self._manual_ids_edit.setPlaceholderText("z. B. 0, 1")
        self._manual_ids_edit.setVisible(False)
        self._manual_ids_error_label = QLabel("")
        self._manual_ids_error_label.setWordWrap(True)
        self._manual_ids_error_label.setStyleSheet("color: red;")
        self._manual_ids_error_label.setVisible(False)

        phonebook_box = QGroupBox("Telefonbücher")
        phonebook_layout = QVBoxLayout(phonebook_box)
        phonebook_layout.addWidget(self._phonebook_explanation_label)
        phonebook_layout.addWidget(self._all_phonebooks_checkbox)
        phonebook_layout.addLayout(self._phonebook_list_layout)
        phonebook_layout.addWidget(self._manual_ids_edit)
        phonebook_layout.addWidget(self._manual_ids_error_label)

        form = QFormLayout()
        form.addRow("Sync-Intervall", self._interval_spin)
        form.addRow(self._popup_checkbox)
        form.addRow(self._minimize_to_tray_checkbox)

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
        self._manual_ids_edit.setEnabled(not checked)

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
        """Kein list_phonebooks_fn (keine Zugangsdaten) oder Ladefehler - Namen können
        nicht aufgelöst werden, daher bleibt nur die Checkbox-Liste deaktiviert. "Alle
        Telefonbücher einbeziehen" bleibt wählbar (braucht keine Box-Verbindung), und
        ein manuelles ID-Eingabefeld füllt die Lücke für alles andere."""
        self._phonebook_status_label.setText(message)
        self._manual_entry_active = True
        self._manual_ids_edit.setVisible(True)
        self._manual_ids_edit.setText(
            ", ".join(str(pid) for pid in sorted(self._existing_phonebook_ids))
        )
        self._manual_ids_edit.setEnabled(not self._all_phonebooks_checkbox.isChecked())

    @staticmethod
    def _parse_manual_ids(text: str) -> list[int] | None:
        """Kommagetrennte IDs -> Liste; None bei ungültigem oder leerem Ergebnis (eine
        leere Liste würde beim Speichern "alle Telefonbücher" bedeuten, was der
        deaktivierten "Alle"-Checkbox widerspräche - siehe accept())."""
        ids: list[int] = []
        for token in text.split(","):
            token = token.strip()
            if not token:
                continue
            if not token.isdigit():
                return None
            ids.append(int(token))
        return ids or None

    def accept(self) -> None:
        if self._manual_entry_active and not self._all_phonebooks_checkbox.isChecked():
            parsed = self._parse_manual_ids(self._manual_ids_edit.text())
            if parsed is None:
                self._manual_ids_error_label.setText(
                    "Bitte gültige, kommagetrennte Telefonbuch-IDs angeben, oder "
                    "'Alle Telefonbücher einbeziehen' aktivieren."
                )
                self._manual_ids_error_label.setVisible(True)
                return
            self._manual_ids_error_label.setVisible(False)
            self._parsed_manual_ids = parsed
        super().accept()

    def save(self, base: Config) -> Config:
        phonebook_ids = base.phonebook_ids
        if self._phonebooks_loaded:
            phonebook_ids = (
                []
                if self._all_phonebooks_checkbox.isChecked()
                else [pid for pid, checkbox in self._phonebook_checkboxes if checkbox.isChecked()]
            )
        elif self._manual_entry_active:
            phonebook_ids = (
                [] if self._all_phonebooks_checkbox.isChecked() else self._parsed_manual_ids
            )
        new_config = replace(
            base,
            sync_interval_minutes=self._interval_spin.value(),
            show_incoming_call_popup=self._popup_checkbox.isChecked(),
            minimize_to_tray_on_close=self._minimize_to_tray_checkbox.isChecked(),
            phonebook_ids=phonebook_ids,
        )
        config_module.save(new_config)
        return new_config
