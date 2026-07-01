from fritz_callhistory.config import Config
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
