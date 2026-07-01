"""Dünner Wrapper um fritzconnection: Verbindung, Anrufliste, Telefonbuch.

Übersetzt fritzconnection/requests-Fehler in die eigenen Exception-Typen, damit
Sync-Service und GUI nur gegen FritzBoxError-Subklassen behandeln müssen.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TypeVar

import requests
from fritzconnection import FritzConnection
from fritzconnection.core.exceptions import FritzAuthorizationError, FritzConnectionException
from fritzconnection.lib.fritzcall import Call, FritzCall
from fritzconnection.lib.fritzphonebook import FritzPhonebook

from fritz_callhistory.fritz.exceptions import (
    FritzBoxAuthError,
    FritzBoxConnectionError,
    FritzBoxPermissionError,
)

_NETWORK_EXCEPTIONS = (FritzConnectionException, requests.exceptions.RequestException)
_MAX_ATTEMPTS = 2
_RETRY_DELAY_SECONDS = 1.0

_T = TypeVar("_T")


def _retry_network(fn, *args, **kwargs) -> _T:
    """Ruft fn(*args, **kwargs) auf, mit einem Retry bei transienten Verbindungs-
    fehlern (z.B. abgelaufene Session, kurzer Netzwerkausfall). Rechte-/Login-
    Fehler (FritzAuthorizationError) werden unverändert durchgereicht, da sie
    kein Netzwerkproblem sind und ein Retry nichts daran ändern würde."""
    last_error: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            return fn(*args, **kwargs)
        except FritzAuthorizationError:
            raise
        except _NETWORK_EXCEPTIONS as exc:
            last_error = exc
            if attempt + 1 < _MAX_ATTEMPTS:
                time.sleep(_RETRY_DELAY_SECONDS)
    assert last_error is not None
    raise last_error


@dataclass
class FritzBoxInfo:
    modelname: str
    system_version: str


class FritzBoxClient:
    def __init__(self, address: str, user: str, password: str) -> None:
        try:
            self._connection = _retry_network(
                FritzConnection, address=address, user=user, password=password
            )
        except FritzAuthorizationError as exc:
            raise FritzBoxAuthError(str(exc)) from exc
        except _NETWORK_EXCEPTIONS as exc:
            raise FritzBoxConnectionError(str(exc)) from exc

        self._call = FritzCall(self._connection)
        self._phonebook = FritzPhonebook(self._connection)

    def info(self) -> FritzBoxInfo:
        return FritzBoxInfo(
            modelname=self._connection.modelname,
            system_version=self._connection.system_version,
        )

    def get_calls(self, *, num: int | None = None, days: int | None = None) -> list[Call]:
        try:
            return _retry_network(self._call.get_calls, num=num, days=days)
        except FritzAuthorizationError as exc:
            raise FritzBoxPermissionError(
                "Fehlendes Fritz!Box-Benutzerrecht: 'Sprachnachrichten, Fax, "
                "Anrufliste und FRITZ!App Fon'"
            ) from exc
        except _NETWORK_EXCEPTIONS as exc:
            raise FritzBoxConnectionError(str(exc)) from exc

    def phonebook_ids(self) -> list[int]:
        try:
            return list(_retry_network(lambda: self._phonebook.phonebook_ids))
        except _NETWORK_EXCEPTIONS as exc:
            raise FritzBoxConnectionError(str(exc)) from exc

    def phonebook_name_numbers(self, phonebook_id: int) -> list[tuple[str, list[str]]]:
        try:
            return _retry_network(self._phonebook.get_all_name_numbers, phonebook_id)
        except _NETWORK_EXCEPTIONS as exc:
            raise FritzBoxConnectionError(str(exc)) from exc
