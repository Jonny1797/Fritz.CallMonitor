"""Holt Anrufe von der Fritz!Box und schreibt neue Einträge dauerhaft lokal fest."""

from __future__ import annotations

import sqlite3

from fritz_callhistory.db.repository import (
    CallRepository,
    ContactRepository,
    LocalPhonebookRepository,
    PhonebookRepository,
    VoicemailRepository,
)
from fritz_callhistory.fritz.client import FritzBoxClient
from fritz_callhistory.sync.caller_directory import CallerDirectory
from fritz_callhistory.sync.normalize import normalize_number


class SyncService:
    def __init__(
        self,
        client: FritzBoxClient,
        contacts: ContactRepository,
        calls: CallRepository,
        phonebook: PhonebookRepository,
        local_phonebook: LocalPhonebookRepository,
        voicemail: VoicemailRepository,
        connection: sqlite3.Connection,
    ) -> None:
        self._client = client
        self._contacts = contacts
        self._calls = calls
        self._phonebook = phonebook
        self._local_phonebook = local_phonebook
        self._voicemail = voicemail
        self._conn = connection

    def sync_calls(self, *, days: int | None = None) -> int:
        """Holt Anrufe von der Box und übernimmt neue Einträge in die lokale DB.

        Gibt die Anzahl tatsächlich neu eingefügter Anrufe zurück (Duplikate,
        die schon aus einem früheren Sync bekannt sind, werden übersprungen).
        """
        remote_calls = self._client.get_calls(days=days)
        inserted = 0
        for call in remote_calls:
            normalized_number, is_anonymous = normalize_number(call.counterparty_number)
            contact_id = self._contacts.upsert(
                normalized_number, is_anonymous=is_anonymous, commit=False
            )

            was_inserted = self._calls.insert(
                contact_id=contact_id,
                call_type=call.call_type,
                caller_number=call.caller_number,
                called_number=call.called_number,
                port=call.port,
                device=call.device,
                call_date=call.call_date,
                duration_seconds=call.duration_seconds,
                raw_name=call.name,
                box_call_id=call.box_call_id,
                commit=False,
            )
            if was_inserted:
                inserted += 1
        # Ein Commit für den gesamten Sync statt einem pro Anruf (siehe
        # docs/improvements.md #4) - unproblematisch, da ein Sync idempotent
        # und jederzeit gefahrlos wiederholbar ist: ein abgebrochener Sync
        # holt beim naechsten Mal einfach dieselben Anrufe erneut.
        self._conn.commit()
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
                    commit=False,
                )
                if was_inserted:
                    inserted += 1
        self._voicemail.prune_missing(seen_keys, queried_tam_indices, commit=False)
        # Ein Commit für den gesamten Sync statt einem pro Nachricht (siehe
        # docs/improvements.md #4), aus demselben Idempotenz-Grund wie in
        # sync_calls().
        self._conn.commit()
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

        return CallerDirectory(
            self._contacts, self._phonebook, self._local_phonebook
        ).refresh_names()
