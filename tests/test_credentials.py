from fritz_callhistory import credentials


def test_set_and_get_password_uses_keyring(mocker):
    mock_set = mocker.patch("keyring.set_password")
    mock_get = mocker.patch("keyring.get_password", return_value="secret")

    credentials.set_password("admin", "secret")
    result = credentials.get_password("admin")

    mock_set.assert_called_once_with("fritz-callhistory", "admin", "secret")
    mock_get.assert_called_once_with("fritz-callhistory", "admin")
    assert result == "secret"


def test_delete_password_ignores_missing_entry(mocker):
    import keyring.errors

    mocker.patch("keyring.delete_password", side_effect=keyring.errors.PasswordDeleteError)

    credentials.delete_password("admin")  # darf nicht raisen
