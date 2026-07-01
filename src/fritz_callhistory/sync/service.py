"""Holt Anrufe von der Fritz!Box und schreibt neue Einträge dauerhaft lokal fest."""

from __future__ import annotations

import datetime

from fritzconnection.lib.fritzcall import ACTIVE_OUT_CALL_TYPE, OUT_CALL_TYPE, Call

from fritz_callhistory.db.repository import CallRepository, ContactRepository, PhonebookRepository
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


class SyncService:
    def __init__(
        self,
        client: FritzBoxClient,
        contacts: ContactRepository,
        calls: CallRepository,
        phonebook: PhonebookRepository,
    ) -> None:
        self._client = client
        self._contacts = contacts
        self._calls = calls
        self._phonebook = phonebook

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
                device=call.Device,
                call_date=_call_date_iso(call),
                duration_seconds=_duration_seconds(call),
                raw_name=call.Name,
            )
            if was_inserted:
                inserted += 1
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

        updated = 0
        for contact in self._contacts.search(""):
            name = self._phonebook.lookup_name(contact.primary_number)
            if name and name != contact.display_name:
                self._contacts.set_display_name(contact.id, name)
                updated += 1
        return updated
