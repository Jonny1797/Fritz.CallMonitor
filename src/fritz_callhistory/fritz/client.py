"""Dünner Wrapper um fritzconnection: Verbindung, Anrufliste, Telefonbuch.

Übersetzt fritzconnection/requests-Fehler in die eigenen Exception-Typen, damit
Sync-Service und GUI nur gegen FritzBoxError-Subklassen behandeln müssen.
"""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
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
# SyncWorker/ImportFromBoxWorker unter Umständen für immer in ihrem
# Netzwerkaufruf hängen, was wiederum MainWindow.closeEvent()'s Warten auf den
# Thread beim Beenden unbegrenzt blockierte (die App "hängte" beim Quit).
_REQUEST_TIMEOUT_SECONDS = 15.0

_T = TypeVar("_T")


def _install_default_session_timeout(session: requests.Session) -> None:
    """FritzConnection versorgt SOAP-Aufrufe (soaper/device_manager) intern mit dem
    beim Konstruktor übergebenen timeout, aber HttpInterface.call_url() (genutzt von
    voicemail_audio() für den download.lua-Abruf) reicht keinen Timeout durch - dessen
    Signatur nimmt nur (url, payload) entgegen und ruft darunter session.get() ohne
    timeout auf. requests kennt keinen Session-weiten Default, daher wird hier
    session.request() gewrappt, um jedem Aufruf über diese Session einen Timeout
    aufzuzwingen, falls keiner explizit gesetzt ist."""
    original_request = session.request

    def request_with_timeout(*args, **kwargs):
        kwargs.setdefault("timeout", _REQUEST_TIMEOUT_SECONDS)
        return original_request(*args, **kwargs)

    session.request = request_with_timeout


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


@dataclass
class VoicemailMessage:
    tam_index: int
    box_index: int  # <Index> - nicht stabil über Löschungen hinweg, nur für Anzeige/Reihenfolge
    caller_number: str | None
    called_number: str | None
    date: str  # ISO8601, umgewandelt aus der Box-Zeitstempelform "%d.%m.%y %H:%M"
    duration_seconds: int | None
    name: str | None
    path: str  # relativer <Path>, z.B. "/download.lua?path=/data/tam/rec/rec.0.000" - Dedupe-Key
    is_new: bool


def _parse_duration_seconds(duration: str | None) -> int | None:
    """Box liefert die Nachrichtendauer bereits als "M:SS"-String (verifiziert gegen
    eine echte Box) - anders als bei regulären Anrufen ("H:MM", siehe fritzconnection's
    timedelta_converter) und schliesst offenbar das feste Anruf-/Verbindungsgeräusch am
    Anfang/Ende der Aufnahme aus. Wird unverändert übernommen statt selbst aus der
    Audiodatei berechnet - gleiches Vertrauensmodell wie bei Call.Duration."""
    if not duration:
        return None
    minutes, seconds = duration.split(":", 1)
    return int(minutes) * 60 + int(seconds)


def _parse_message_date_iso(date: str) -> str:
    """Box liefert "%d.%m.%y %H:%M" (gleiches Format wie fritzconnection.lib.fritzcall's
    Call.Date) - für konsistente Speicherung/Sortierung in ISO8601 umgewandelt, wie
    sync/service.py's _call_date_iso() es für reguläre Anrufe bereits tut."""
    return datetime.strptime(date, "%d.%m.%y %H:%M").isoformat()


def _parse_voicemail_messages(root: ET.Element, tam_index: int) -> list[VoicemailMessage]:
    messages = []
    for message_el in root.iter("Message"):
        fields = {child.tag: (child.text or "").strip() for child in message_el}
        messages.append(
            VoicemailMessage(
                tam_index=tam_index,
                box_index=int(fields.get("Index", "0")),
                caller_number=fields.get("Number") or None,
                called_number=fields.get("Called") or None,
                date=_parse_message_date_iso(fields.get("Date", "")),
                duration_seconds=_parse_duration_seconds(fields.get("Duration")),
                name=fields.get("Name") or None,
                path=fields.get("Path", ""),
                is_new=fields.get("New") == "1",
            )
        )
    return messages


def _parse_phonebook_contacts(root: ET.Element) -> list[FritzPhonebookContact]:
    """Eigenes, minimales XML-Parsing der Box-Telefonbuch-Antwort.

    fritzconnection.lib.fritzphonebook's eigener Prozessor (core/processor.py)
    liest nur Element-Text, nie XML-Attribute - number/@type geht dadurch
    verloren, obwohl uniqueid/category (Kind-Elemente mit Text) erhalten
    bleiben. Für den Box-Import brauchen wir Nummern-Typ UND uniqueid, daher
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

        _install_default_session_timeout(self._connection.session)
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
        """Löst einen Anruf über die Box-Wählhilfe aus (X_AVM-DE_DialNumber):
        die Box ruft *number* an und lässt dann das angeschlossene Telefon klingeln."""
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

    def voicemail_tam_indices(self) -> list[int]:
        """Ermittelt die aktivierten Anrufbeantworter-Slots (X_AVM-DE_TAM/GetList).

        fritzconnection hat keine eigene Helper-Klasse für diesen Dienst (anders als
        FritzCall/FritzPhonebook), daher direkter call_action(). GetList() braucht kein
        Argument und liefert NewTAMList als eigenen, verschachtelten XML-String mit einem
        <Item> je Box-Slot (die Box hat fest 5 Slots, Index 0-4)."""
        try:
            result = _retry_network(self._connection.call_action, "X_AVM-DE_TAM", "GetList")
        except FritzAuthorizationError as exc:
            raise FritzBoxPermissionError(
                "Fehlendes Fritz!Box-Benutzerrecht: 'Sprachnachrichten, Fax, "
                "Anrufliste und FRITZ!App Fon'"
            ) from exc
        except _NETWORK_EXCEPTIONS as exc:
            raise FritzBoxConnectionError(str(exc)) from exc
        root = ET.fromstring(result["NewTAMList"])
        return [
            int(item.findtext("Index"))
            for item in root.iter("Item")
            if item.findtext("Enable") == "1"
        ]

    def voicemail_messages(self, tam_index: int) -> list[VoicemailMessage]:
        """Nachrichtenliste eines Anrufbeantworter-Slots (X_AVM-DE_TAM/GetMessageList):
        gleiches Muster wie phonebook_contacts_detailed() - Action liefert eine URL,
        die per get_xml_root() abgerufen und selbst geparst wird (kein eingebauter
        fritzconnection-Prozessor für diesen Dienst)."""
        try:
            result = _retry_network(
                self._connection.call_action, "X_AVM-DE_TAM", "GetMessageList", NewIndex=tam_index
            )
            root = _retry_network(
                get_xml_root,
                result["NewURL"],
                session=self._connection.session,
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )
        except FritzAuthorizationError as exc:
            raise FritzBoxPermissionError(
                "Fehlendes Fritz!Box-Benutzerrecht: 'Sprachnachrichten, Fax, "
                "Anrufliste und FRITZ!App Fon'"
            ) from exc
        except _NETWORK_EXCEPTIONS as exc:
            raise FritzBoxConnectionError(str(exc)) from exc
        return _parse_voicemail_messages(root, tam_index)

    def voicemail_audio(self, path: str) -> bytes:
        """Lädt die Audiodatei einer Nachricht (relativer *path* aus einer
        VoicemailMessage, z.B. "/download.lua?path=/data/tam/rec/rec.0.000").

        download.lua läuft nur auf dem TR-064-Port (verifiziert: Port 80 liefert 404),
        und verlangt dort eine gültige Session-ID als Query-Parameter statt der
        HTTP-Digest-Auth, die für SOAP-Aufrufe reicht. self._connection.http_interface
        (fritzconnection's AHA-HTTP-Interface-Login) holt/erneuert diese Session-ID
        selbst und hängt sie an - dessen call_url() ist zwar laut eigenem Docstring
        auch für "undokumentierte Endpunkte" gedacht (weniger stabil als TR-064 SOAP),
        aber die einzige offizielle Methode in fritzconnection, die den Login-Handshake
        für einen selbst gewählten Pfad wie download.lua übernimmt."""
        query = path.split("?", 1)[1] if "?" in path else path
        params = dict(pair.split("=", 1) for pair in query.split("&") if "=" in pair)
        url = f"{self._connection.address}:{self._connection.port}/download.lua"
        try:
            response = _retry_network(self._connection.http_interface.call_url, url, params)
        except FritzAuthorizationError as exc:
            raise FritzBoxPermissionError(
                "Fehlendes Fritz!Box-Benutzerrecht: 'Sprachnachrichten, Fax, "
                "Anrufliste und FRITZ!App Fon'"
            ) from exc
        except _NETWORK_EXCEPTIONS as exc:
            raise FritzBoxConnectionError(str(exc)) from exc
        return response.content

    def voicemail_mark_read(self, tam_index: int, message_index: int) -> None:
        """Markiert eine Nachricht auf der Box selbst als gelesen (X_AVM-DE_TAM/
        MarkMessage) - verifiziert gegen eine echte Box, reversibel (NewMarkedAsRead
        0/1). Wird beim Abspielen in der GUI aufgerufen, damit der "neu"-Zustand
        konsistent mit der Box bleibt statt nur durch ein Handset aktualisierbar zu sein."""
        try:
            _retry_network(
                self._connection.call_action,
                "X_AVM-DE_TAM",
                "MarkMessage",
                NewIndex=tam_index,
                NewMessageIndex=message_index,
                NewMarkedAsRead=1,
            )
        except FritzAuthorizationError as exc:
            raise FritzBoxPermissionError(
                "Fehlendes Fritz!Box-Benutzerrecht: 'Sprachnachrichten, Fax, "
                "Anrufliste und FRITZ!App Fon'"
            ) from exc
        except _NETWORK_EXCEPTIONS as exc:
            raise FritzBoxConnectionError(str(exc)) from exc

    def voicemail_delete(self, tam_index: int, message_index: int) -> None:
        """Löscht eine Nachricht auf der Box selbst (X_AVM-DE_TAM/DeleteMessage) -
        verifiziert gegen eine echte Box, nicht umkehrbar. message_index ist wie bei
        voicemail_mark_read() der Box-eigene <Index>, der nicht stabil über
        Löschungen hinweg ist - Aufrufer müssen ihn unmittelbar vor diesem Aufruf
        über voicemail_messages() neu auflösen."""
        try:
            _retry_network(
                self._connection.call_action,
                "X_AVM-DE_TAM",
                "DeleteMessage",
                NewIndex=tam_index,
                NewMessageIndex=message_index,
            )
        except FritzAuthorizationError as exc:
            raise FritzBoxPermissionError(
                "Fehlendes Fritz!Box-Benutzerrecht: 'Sprachnachrichten, Fax, "
                "Anrufliste und FRITZ!App Fon'"
            ) from exc
        except _NETWORK_EXCEPTIONS as exc:
            raise FritzBoxConnectionError(str(exc)) from exc

    def phonebook_contacts_detailed(self, phonebook_id: int) -> list[FritzPhonebookContact]:
        """Wie phonebook_name_numbers(), aber inkl. uniqueid/category/Nummern-Typ
        - für den einmaligen "Von Box importieren"-Zug ins lokale Telefonbuch."""
        try:
            url = _retry_network(self._phonebook.phonebook_info, phonebook_id)["url"]
            root = _retry_network(
                get_xml_root, url, session=self._connection.session, timeout=_REQUEST_TIMEOUT_SECONDS
            )
        except _NETWORK_EXCEPTIONS as exc:
            raise FritzBoxConnectionError(str(exc)) from exc
        return _parse_phonebook_contacts(root)
