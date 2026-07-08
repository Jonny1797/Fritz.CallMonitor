"""Dünner Wrapper um fritzconnection: Verbindung, Anrufliste, Telefonbuch.

Übersetzt fritzconnection/requests-Fehler in die eigenen Exception-Typen, damit
Sync-Service und GUI nur gegen FritzBoxError-Subklassen behandeln müssen.
"""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import TypeVar

import requests
from fritzconnection import FritzConnection
from fritzconnection.core.exceptions import FritzAuthorizationError, FritzConnectionException
from fritzconnection.core.utils import get_xml_root
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
# fritzconnection/requests haben ohne dieses Limit gar kein Timeout (blockieren
# unbegrenzt, wenn die Box verbunden ist aber nicht antwortet) - das liess
# SyncWorker/ImportFromBoxWorker unter Umstaenden fuer immer in ihrem
# Netzwerkaufruf haengen, was wiederum MainWindow.closeEvent()'s Warten auf den
# Thread beim Beenden unbegrenzt blockierte (die App "haengte" beim Quit).
_REQUEST_TIMEOUT_SECONDS = 15.0

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


@dataclass
class FritzPhonebookNumber:
    value: str
    type: str


@dataclass
class FritzPhonebookContact:
    uniqueid: str | None
    name: str | None
    category: str | None
    numbers: list[FritzPhonebookNumber] = field(default_factory=list)


def _parse_phonebook_contacts(root: ET.Element) -> list[FritzPhonebookContact]:
    """Eigenes, minimales XML-Parsing der Box-Telefonbuch-Antwort.

    fritzconnection.lib.fritzphonebook's eigener Prozessor (core/processor.py)
    liest nur Element-Text, nie XML-Attribute - number/@type geht dadurch
    verloren, obwohl uniqueid/category (Kind-Elemente mit Text) erhalten
    bleiben. Fuer den Box-Import brauchen wir Nummern-Typ UND uniqueid, daher
    hier ein eigener, schlanker Parse-Schritt statt FritzPhonebook.get_all_name_numbers().
    """
    contacts = []
    for contact_el in root.iter("contact"):
        name_el = contact_el.find("person/realName")
        uniqueid_el = contact_el.find("uniqueid")
        category_el = contact_el.find("category")
        numbers = []
        for number_el in contact_el.findall("telephony/number"):
            value = (number_el.text or "").strip()
            if value:
                numbers.append(
                    FritzPhonebookNumber(value=value, type=number_el.get("type") or "home")
                )
        contacts.append(
            FritzPhonebookContact(
                uniqueid=(uniqueid_el.text or "").strip()
                if uniqueid_el is not None and uniqueid_el.text
                else None,
                name=(name_el.text or "").strip() if name_el is not None and name_el.text else None,
                category=(category_el.text or "").strip() if category_el is not None else None,
                numbers=numbers,
            )
        )
    return contacts


class FritzBoxClient:
    def __init__(self, address: str, user: str, password: str) -> None:
        try:
            self._connection = _retry_network(
                FritzConnection,
                address=address,
                user=user,
                password=password,
                timeout=_REQUEST_TIMEOUT_SECONDS,
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

    def dial_number(self, number: str) -> None:
        """Loest einen Anruf ueber die Box-Waehlhilfe aus (X_AVM-DE_DialNumber):
        die Box ruft *number* an und laesst dann das angeschlossene Telefon klingeln."""
        try:
            _retry_network(self._call.dial, number)
        except FritzAuthorizationError as exc:
            raise FritzBoxPermissionError(
                "Fehlendes Fritz!Box-Benutzerrecht für die Wählhilfe (X_AVM-DE_DialNumber)"
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

    def phonebook_contacts_detailed(self, phonebook_id: int) -> list[FritzPhonebookContact]:
        """Wie phonebook_name_numbers(), aber inkl. uniqueid/category/Nummern-Typ
        - fuer den einmaligen "Von Box importieren"-Zug ins lokale Telefonbuch."""
        try:
            url = _retry_network(self._phonebook.phonebook_info, phonebook_id)["url"]
            root = _retry_network(
                get_xml_root, url, session=self._connection.session, timeout=_REQUEST_TIMEOUT_SECONDS
            )
        except _NETWORK_EXCEPTIONS as exc:
            raise FritzBoxConnectionError(str(exc)) from exc
        return _parse_phonebook_contacts(root)
