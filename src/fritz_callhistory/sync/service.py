"""Holt Anrufe von der Fritz!Box und schreibt neue Einträge dauerhaft lokal fest."""

from __future__ import annotations

import datetime

from fritzconnection.lib.fritzcall import ACTIVE_OUT_CALL_TYPE, OUT_CALL_TYPE, Call

from fritz_callhistory.db.repository import (
    CallRepository,
    ContactRepository,
    LocalPhonebookRepository,
    PhonebookRepository,
    VoicemailRepository,
)
from fritz_callhistory.fritz.client import FritzBoxClient
from fritz_callhistory.sync.normalize import normalize_number

_OUTGOING_TYPES = {OUT_CALL_TYPE, ACTIVE_OUT_CALL_TYPE}


def _counterparty_number(call: Call) -> str | None:
    """Nummer der Gegenseite - bei ausgehenden Anrufen die angerufene, sonst die anrufende."""
    if call.type in _OUTGOING_TYPES:
        return call.CalledNumber or call.Called
    return call.CallerNumber or call.Caller


def _duration_seconds(call: Call) -> int | None:
    duration = call.duration
    if isinstance(duration, datetime.timedelta):
        return int(duration.total_seconds())
    return None


def _call_date_iso(call: Call) -> str:
    date = call.date
    if isinstance(date, datetime.datetime):
        return date.isoformat()
    return str(call.Date)


def resolve_contact_names(
    contacts: ContactRepository,
    phonebook: PhonebookRepository,
    local_phonebook: LocalPhonebookRepository,
) -> int:
    """Aktualisiert contacts.display_name aus dem lokalen Telefonbuch und dem
    Box-Telefonbuch-Cache. Das lokale Telefonbuch hat Vorrang, da vom Nutzer
    gepflegt (der Box-Cache wird komplett überschrieben bei jedem Sync).

    Kein Netzwerkzugriff, daher bewusst eine freie Funktion statt einer
    SyncService-Methode - kann auch von der GUI direkt nach lokalen
    Telefonbuch-Aenderungen aufgerufen werden, ohne SyncService/FritzBoxClient.

    Lädt beide Telefonbücher einmalig komplett (statt pro Kontakt einzeln
    nachzuschlagen) und schreibt alle geänderten Anzeigenamen in einer einzigen
    Transaktion - für N Kontakte 2 Queries + 1 Commit statt bis zu 3N.
    """
    local_names = local_phonebook.all_names()
    box_names = phonebook.all_names()
    updates: dict[int, str] = {}
    for contact in contacts.search(""):
        name = local_names.get(contact.primary_number) or box_names.get(contact.primary_number)
        if name and name != contact.display_name:
            updates[contact.id] = name
    contacts.set_display_names(updates)
    return len(updates)


class SyncService:
    def __init__(
        self,
        client: FritzBoxClient,
        contacts: ContactRepository,
        calls: CallRepository,
        phonebook: PhonebookRepository,
        local_phonebook: LocalPhonebookRepository,
        voicemail: VoicemailRepository,
    ) -> None:
        self._client = client
        self._contacts = contacts
        self._calls = calls
        self._phonebook = phonebook
        self._local_phonebook = local_phonebook
        self._voicemail = voicemail

    def sync_calls(self, *, days: int | None = None) -> int:
        """Holt Anrufe von der Box und übernimmt neue Einträge in die lokale DB.

        Gibt die Anzahl tatsächlich neu eingefügter Anrufe zurück (Duplikate,
        die schon aus einem früheren Sync bekannt sind, werden übersprungen).
        """
        remote_calls = self._client.get_calls(days=days)
        inserted = 0
        for call in remote_calls:
            normalized_number, is_anonymous = normalize_number(_counterparty_number(call))
            contact_id = self._contacts.upsert(normalized_number, is_anonymous=is_anonymous)

            was_inserted = self._calls.insert(
                contact_id=contact_id,
                call_type=call.type,
                caller_number=call.CallerNumber or call.Caller,
                called_number=call.CalledNumber or call.Called,
                port=call.Port,
                # Die Box sendet "-1" im <Device>-Feld, wenn kein Gerät zutrifft
                # (z.B. abgelehnte/nicht angenommene Anrufe) - als NULL speichern.
                device=call.Device if call.Device not in (None, "-1") else None,
                call_date=_call_date_iso(call),
                duration_seconds=_duration_seconds(call),
                raw_name=call.Name,
                box_call_id=call.id,
            )
            if was_inserted:
                inserted += 1
        return inserted

    def sync_voicemail(self) -> int:
        """Holt Anrufbeantworter-Nachrichten aller aktivierten Slots, übernimmt neue
        Einträge in die lokale DB (siehe VoicemailRepository.insert_or_update für die
        is_new-Refresh-Semantik bei bereits bekannten Nachrichten) und entfernt lokale
        Nachrichten, die auf der Box nicht mehr existieren (z.B. an einem Telefon
        gelöscht) - siehe VoicemailRepository.prune_missing. Das Pruning läuft nur
        nach einem vollständig erfolgreichen Durchlauf aller aktivierten Slots: ein
        Fehler mittendrin propagiert als FritzBoxError und lässt diese Methode gar
        nicht erst bis zum prune_missing()-Aufruf kommen.

        Gibt die Anzahl tatsächlich neu eingefügter Nachrichten zurück.
        """
        inserted = 0
        seen_keys: set[tuple[int, str, str]] = set()
        queried_tam_indices: set[int] = set()
        for tam_index in self._client.voicemail_tam_indices():
            queried_tam_indices.add(tam_index)
            for message in self._client.voicemail_messages(tam_index):
                seen_keys.add((tam_index, message.path, message.date))
                was_inserted = self._voicemail.insert_or_update(
                    tam_index=tam_index,
                    box_path=message.path,
                    caller_number=message.caller_number,
                    called_number=message.called_number,
                    message_date=message.date,
                    duration_seconds=message.duration_seconds,
                    raw_name=message.name,
                    is_new=message.is_new,
                )
                if was_inserted:
                    inserted += 1
        self._voicemail.prune_missing(seen_keys, queried_tam_indices)
        return inserted

    def sync_phonebook(self, phonebook_ids: list[int] | None = None) -> int:
        """Aktualisiert den Telefonbuch-Cache und löst Kontakt-Anzeigenamen neu auf.

        *phonebook_ids* schränkt die einbezogenen Telefonbücher ein (Konfiguration);
        ohne Angabe werden alle auf der Box vorhandenen Telefonbücher genutzt. Gibt
        die Anzahl der Kontakte zurück, deren Anzeigename sich geändert hat.
        """
        ids = phonebook_ids if phonebook_ids is not None else self._client.phonebook_ids()
        for phonebook_id in ids:
            entries: list[tuple[str, str]] = []
            for name, numbers in self._client.phonebook_name_numbers(phonebook_id):
                for number in numbers:
                    normalized, is_anonymous = normalize_number(number)
                    if is_anonymous:
                        continue
                    entries.append((name, normalized))
            self._phonebook.replace_entries(phonebook_id, entries)

        return resolve_contact_names(self._contacts, self._phonebook, self._local_phonebook)
