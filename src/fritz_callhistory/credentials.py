"""Fritz!Box-Passwort im OS-Schlüsselbund (Windows Credential Manager / macOS
Keychain / Linux Secret Service) statt im Klartext auf der Platte."""

from __future__ import annotations

import keyring

_SERVICE_NAME = "fritz-callhistory"


def get_password(username: str) -> str | None:
    return keyring.get_password(_SERVICE_NAME, username)


def set_password(username: str, password: str) -> None:
    keyring.set_password(_SERVICE_NAME, username, password)


def delete_password(username: str) -> None:
    try:
        keyring.delete_password(_SERVICE_NAME, username)
    except keyring.errors.PasswordDeleteError:
        pass
