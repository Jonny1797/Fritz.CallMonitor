"""Ersteinrichtungsdialog: Fritz!Box-Adresse, Benutzername und Passwort erfassen.

Das Passwort landet ausschließlich im OS-Schlüsselbund (siehe credentials.py),
die restliche Konfiguration in der Config-TOML-Datei.
"""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QVBoxLayout

from fritz_callhistory import config as config_module
from fritz_callhistory import credentials
from fritz_callhistory.config import Config


class CredentialsDialog(QDialog):
    def __init__(self, config: Config, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Fritz!Box-Zugangsdaten")

        self._address_edit = QLineEdit(config.address)
        self._username_edit = QLineEdit(config.username)
        self._password_edit = QLineEdit()
        self._password_edit.setEchoMode(QLineEdit.EchoMode.Password)

        has_stored_password = bool(config.username and credentials.get_password(config.username))
        self._password_edit.setPlaceholderText("unverändert lassen" if has_stored_password else "")

        form = QFormLayout()
        form.addRow("Fritz!Box-Adresse", self._address_edit)
        form.addRow("Benutzername", self._username_edit)
        form.addRow("Passwort", self._password_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def save(self, base: Config) -> Config:
        """Persistiert Config (ohne Passwort) und Passwort separat im Schlüsselbund."""
        new_config = replace(
            base,
            address=self._address_edit.text().strip(),
            username=self._username_edit.text().strip(),
        )
        password = self._password_edit.text()
        if password:
            credentials.set_password(new_config.username, password)
        config_module.save(new_config)
        return new_config
