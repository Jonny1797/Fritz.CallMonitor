"""Ersteinrichtungsdialog: Fritz!Box-Adresse, Benutzername und Passwort erfassen.

Das Passwort landet ausschließlich im OS-Schlüsselbund (siehe credentials.py),
die restliche Konfiguration in der Config-TOML-Datei.
"""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from fritz_callhistory import config as config_module
from fritz_callhistory import credentials
from fritz_callhistory.config import Config
from fritz_callhistory.fritz.exceptions import (
    FritzBoxAuthError,
    FritzBoxError,
    FritzBoxPermissionError,
)
from fritz_callhistory.gui.background_tasks import BackgroundTasks
from fritz_callhistory.gui.workers import TestCredentialsFn

_TASK_KEY = "credentials-test"


class CredentialsDialog(QDialog):
    def __init__(
        self,
        config: Config,
        background_tasks: BackgroundTasks,
        test_connection_fn: TestCredentialsFn | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Fritz!Box-Zugangsdaten")
        self._test_connection_fn = test_connection_fn
        self._background_tasks = background_tasks
        self._busy = False
        # Nach Abbruch/Schließen wird ein spät eintreffendes Ergebnis verworfen.
        self._discarded = False

        self._address_edit = QLineEdit(config.address)
        self._username_edit = QLineEdit(config.username)
        self._password_edit = QLineEdit()
        self._password_edit.setEchoMode(QLineEdit.EchoMode.Password)

        has_stored_password = bool(config.username and credentials.get_password(config.username))
        self._password_edit.setPlaceholderText("unverändert lassen" if has_stored_password else "")

        self._show_password_checkbox = QCheckBox("Passwort anzeigen")
        self._show_password_checkbox.toggled.connect(self._on_toggle_password_visibility)

        password_row = QWidget()
        password_row_layout = QHBoxLayout(password_row)
        password_row_layout.setContentsMargins(0, 0, 0, 0)
        password_row_layout.addWidget(self._password_edit)
        password_row_layout.addWidget(self._show_password_checkbox)

        form = QFormLayout()
        form.addRow("Fritz!Box-Adresse", self._address_edit)
        form.addRow("Benutzername", self._username_edit)
        form.addRow("Passwort", password_row)

        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        self._status_label.setVisible(False)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self._on_accept_clicked)
        self._buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._status_label)
        layout.addWidget(self._buttons)

    def _on_toggle_password_visibility(self, checked: bool) -> None:
        self._password_edit.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        )

    def _resolve_password(self) -> str:
        typed = self._password_edit.text()
        if typed:
            return typed
        username = self._username_edit.text().strip()
        return credentials.get_password(username) or ""

    def _on_accept_clicked(self) -> None:
        if self._test_connection_fn is None:
            # Kein Verbindungstest injiziert - z.B. in Tests, die diesen Pfad
            # nicht mit abdecken wollen. Altes Verhalten: sofort übernehmen.
            self.accept()
            return

        address = self._address_edit.text().strip()
        username = self._username_edit.text().strip()
        if not address or not username:
            self._show_status("Adresse und Benutzername dürfen nicht leer sein.")
            return
        password = self._resolve_password()

        self._set_busy(True)
        self._show_status("Verbindung wird geprüft …", is_error=False)

        test_connection_fn = self._test_connection_fn
        started = self._background_tasks.start(
            lambda: test_connection_fn(address, username, password),
            self,
            self._on_test_succeeded,
            self._on_test_failed,
            key=_TASK_KEY,
        )
        if not started:
            self._set_busy(False)
            self._status_label.setVisible(False)

    def _set_busy(self, busy: bool) -> None:
        # Cancel bleibt bedienbar: das Ergebnis gehört BackgroundTasks, ein
        # geschlossener Dialog verwirft es einfach (siehe done()).
        self._busy = busy
        self._address_edit.setEnabled(not busy)
        self._username_edit.setEnabled(not busy)
        self._password_edit.setEnabled(not busy)
        self._show_password_checkbox.setEnabled(not busy)
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(not busy)

    def _show_status(self, message: str, *, is_error: bool = True) -> None:
        self._status_label.setStyleSheet("color: red;" if is_error else "")
        self._status_label.setText(message)
        self._status_label.setVisible(True)

    def done(self, result: int) -> None:
        # Jedes Schließen (OK, Cancel, Escape) verwirft ein noch laufendes Prüfergebnis.
        self._discarded = True
        super().done(result)

    def _on_test_succeeded(self, _result: object) -> None:
        if self._discarded:
            return
        self._set_busy(False)
        self._status_label.setVisible(False)
        self.accept()

    def _on_test_failed(self, exc: FritzBoxError) -> None:
        if self._discarded:
            return
        self._set_busy(False)
        message = str(exc)
        if isinstance(exc, FritzBoxAuthError):
            self._show_status(
                f"Anmeldung fehlgeschlagen: Benutzername oder Passwort falsch ({message})"
            )
        elif isinstance(exc, FritzBoxPermissionError):
            # Auf einer echten Box nicht zuverlässig von einem falschen Passwort zu
            # unterscheiden: AVM liefert sowohl für "falsches Passwort" als auch für
            # "richtiges Passwort, aber fehlendes Anrufliste-Recht" denselben
            # Fehlertyp (FritzAuthorizationError -> fritz/client.py's
            # FritzBoxPermissionError) - siehe CLAUDE.md. Deshalb hier NICHT
            # übernehmen, sondern wie einen Anmeldefehler behandeln. *message* nennt
            # bei fehlender Berechtigung bereits das konkrete Fritz!Box-Benutzerrecht
            # (siehe FritzBoxClient.get_calls), daher hier nicht nochmal wiederholen.
            self._show_status(f"Anmeldung fehlgeschlagen oder fehlende Berechtigung: {message}")
        else:
            self._show_status(f"Verbindung fehlgeschlagen: {message}")

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
