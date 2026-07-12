from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QDialog, QLineEdit

from fritz_callhistory.config import Config
from fritz_callhistory.fritz.exceptions import (
    FritzBoxAuthError,
    FritzBoxConnectionError,
    FritzBoxPermissionError,
)
from fritz_callhistory.gui.credentials_dialog import CredentialsDialog


def test_save_persists_config_and_password(qtbot, mocker):
    mock_config_save = mocker.patch("fritz_callhistory.gui.credentials_dialog.config_module.save")
    mock_set_password = mocker.patch("fritz_callhistory.gui.credentials_dialog.credentials.set_password")
    mocker.patch("fritz_callhistory.gui.credentials_dialog.credentials.get_password", return_value=None)

    dialog = CredentialsDialog(Config())
    qtbot.addWidget(dialog)
    dialog._address_edit.setText("192.168.178.1")
    dialog._username_edit.setText("admin")
    dialog._password_edit.setText("secret")

    updated = dialog.save(Config())

    assert updated.address == "192.168.178.1"
    assert updated.username == "admin"
    mock_set_password.assert_called_once_with("admin", "secret")
    mock_config_save.assert_called_once_with(updated)


def test_save_without_password_input_keeps_stored_password(qtbot, mocker):
    mocker.patch(
        "fritz_callhistory.gui.credentials_dialog.credentials.get_password",
        return_value="already-stored",
    )
    mock_set_password = mocker.patch("fritz_callhistory.gui.credentials_dialog.credentials.set_password")
    mocker.patch("fritz_callhistory.gui.credentials_dialog.config_module.save")

    dialog = CredentialsDialog(Config(username="admin"))
    qtbot.addWidget(dialog)
    # Passwortfeld bleibt bewusst leer

    dialog.save(Config(username="admin"))

    mock_set_password.assert_not_called()


def test_show_password_checkbox_toggles_echo_mode(qtbot, mocker):
    mocker.patch("fritz_callhistory.gui.credentials_dialog.credentials.get_password", return_value=None)

    dialog = CredentialsDialog(Config())
    qtbot.addWidget(dialog)

    assert dialog._password_edit.echoMode() == QLineEdit.EchoMode.Password

    dialog._show_password_checkbox.setChecked(True)
    assert dialog._password_edit.echoMode() == QLineEdit.EchoMode.Normal

    dialog._show_password_checkbox.setChecked(False)
    assert dialog._password_edit.echoMode() == QLineEdit.EchoMode.Password


def test_accept_without_test_connection_fn_accepts_immediately(qtbot, mocker):
    mocker.patch("fritz_callhistory.gui.credentials_dialog.credentials.get_password", return_value=None)

    dialog = CredentialsDialog(Config())
    qtbot.addWidget(dialog)

    dialog._on_accept_clicked()

    assert dialog.result() == QDialog.DialogCode.Accepted


def test_accept_runs_connection_test_and_accepts_on_success(qtbot, mocker):
    mocker.patch("fritz_callhistory.gui.credentials_dialog.credentials.get_password", return_value=None)
    test_fn = mocker.Mock(return_value=None)

    dialog = CredentialsDialog(Config(), test_connection_fn=test_fn)
    qtbot.addWidget(dialog)
    dialog._address_edit.setText("192.168.178.1")
    dialog._username_edit.setText("admin")
    dialog._password_edit.setText("secret")

    dialog._on_accept_clicked()
    qtbot.waitUntil(lambda: dialog.result() == QDialog.DialogCode.Accepted, timeout=2000)

    test_fn.assert_called_once_with("192.168.178.1", "admin", "secret")


def test_accept_stays_open_and_shows_error_on_auth_failure(qtbot, mocker):
    mocker.patch("fritz_callhistory.gui.credentials_dialog.credentials.get_password", return_value=None)
    accept_spy = mocker.spy(CredentialsDialog, "accept")

    def failing_test_fn(address, username, password):
        raise FritzBoxAuthError("401 Unauthorized")

    dialog = CredentialsDialog(Config(), test_connection_fn=failing_test_fn)
    qtbot.addWidget(dialog)
    dialog._address_edit.setText("192.168.178.1")
    dialog._username_edit.setText("admin")
    dialog._password_edit.setText("wrong")

    dialog._on_accept_clicked()
    qtbot.waitUntil(lambda: not dialog._busy, timeout=2000)

    accept_spy.assert_not_called()
    assert dialog._buttons.isEnabled()
    assert "Benutzername oder Passwort" in dialog._status_label.text()


def test_accept_stays_open_and_shows_error_on_connection_failure(qtbot, mocker):
    mocker.patch("fritz_callhistory.gui.credentials_dialog.credentials.get_password", return_value=None)
    accept_spy = mocker.spy(CredentialsDialog, "accept")

    def failing_test_fn(address, username, password):
        raise FritzBoxConnectionError("Box nicht erreichbar")

    dialog = CredentialsDialog(Config(), test_connection_fn=failing_test_fn)
    qtbot.addWidget(dialog)
    dialog._address_edit.setText("192.168.178.1")
    dialog._username_edit.setText("admin")
    dialog._password_edit.setText("secret")

    dialog._on_accept_clicked()
    qtbot.waitUntil(lambda: not dialog._busy, timeout=2000)

    accept_spy.assert_not_called()
    assert "Verbindung fehlgeschlagen" in dialog._status_label.text()


def test_accept_stays_open_and_shows_error_on_permission_denied(qtbot, mocker):
    # FritzBoxPermissionError ist auf einer echten Box nicht zuverlässig von
    # einem falschen Passwort zu unterscheiden (siehe CredentialsDialog.
    # _on_test_permission_denied) - darf den Dialog deshalb NICHT schliessen,
    # sonst reproduziert das genau den vom Nutzer gemeldeten Bug (Dialog
    # schliesst trotz falscher Zugangsdaten).
    mocker.patch("fritz_callhistory.gui.credentials_dialog.credentials.get_password", return_value=None)
    accept_spy = mocker.spy(CredentialsDialog, "accept")

    def test_fn(address, username, password):
        raise FritzBoxPermissionError("fehlendes Recht")

    dialog = CredentialsDialog(Config(), test_connection_fn=test_fn)
    qtbot.addWidget(dialog)
    dialog._address_edit.setText("192.168.178.1")
    dialog._username_edit.setText("admin")
    dialog._password_edit.setText("secret")

    dialog._on_accept_clicked()
    qtbot.waitUntil(lambda: not dialog._busy, timeout=2000)

    accept_spy.assert_not_called()
    assert "Anmeldung fehlgeschlagen" in dialog._status_label.text()


def test_accept_with_empty_fields_shows_error_without_calling_test_fn(qtbot, mocker):
    mocker.patch("fritz_callhistory.gui.credentials_dialog.credentials.get_password", return_value=None)
    test_fn = mocker.Mock()

    dialog = CredentialsDialog(Config(), test_connection_fn=test_fn)
    qtbot.addWidget(dialog)
    dialog._address_edit.setText("")
    dialog._username_edit.setText("")

    dialog._on_accept_clicked()

    test_fn.assert_not_called()
    assert "dürfen nicht leer" in dialog._status_label.text()


def test_accept_falls_back_to_stored_password_when_field_left_blank(qtbot, mocker):
    mocker.patch(
        "fritz_callhistory.gui.credentials_dialog.credentials.get_password",
        return_value="already-stored",
    )
    test_fn = mocker.Mock(return_value=None)

    dialog = CredentialsDialog(Config(username="admin"), test_connection_fn=test_fn)
    qtbot.addWidget(dialog)
    dialog._address_edit.setText("192.168.178.1")
    # Passwortfeld bleibt bewusst leer

    dialog._on_accept_clicked()
    qtbot.waitUntil(lambda: dialog.result() == QDialog.DialogCode.Accepted, timeout=2000)

    test_fn.assert_called_once_with("192.168.178.1", "admin", "already-stored")


def test_close_event_ignored_while_connection_test_is_running(qtbot, mocker):
    mocker.patch("fritz_callhistory.gui.credentials_dialog.credentials.get_password", return_value=None)

    dialog = CredentialsDialog(Config(), test_connection_fn=mocker.Mock())
    qtbot.addWidget(dialog)
    dialog._set_busy(True)

    event = QCloseEvent()
    dialog.closeEvent(event)

    assert not event.isAccepted()
