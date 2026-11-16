"""Caller directory: die eine Stelle, die klärt, wer hinter einer Nummer steckt.

Rein (Repositories + Normalisierung), kein Qt, kein Netzwerk. Namensvorrang:
Telefonbuch-Kontakt, dann Box-Telefonbuch, sonst kein Name. Bei mehreren
Telefonbuch-Kontakten mit derselben Nummer gewinnt die niedrigste id (Name und
Notizen). Notizen kommen nur aus dem Telefonbuch-Kontakt. Kein Cache.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from fritz_callhistory.db.repository import (
    ContactRepository,
    LocalPhonebookRepository,
    PhonebookRepository,
    number_search_spellings,
)
from fritz_callhistory.sync.normalize import format_number_display, normalize_number

ANONYMOUS_LABEL = "Anonym / unterdrückt"


@dataclass(frozen=True)
class CallerIdentity:
    number: str
    is_anonymous: bool
    name: str | None
    notes: str | None
    caller_id: int | None

    def label(self, fallback_name: str | None = None) -> str:
        """Name, sonst fallback_name, sonst formatierte Nummer, sonst "Anonym / unterdrückt"."""
        if self.name:
            return self.name
        if fallback_name:
            return fallback_name
        if not self.is_anonymous:
            formatted = format_number_display(self.number)
            if formatted:
                return formatted
        return ANONYMOUS_LABEL


class CallerDirectory:
    def __init__(
        self,
        contacts: ContactRepository,
        phonebook: PhonebookRepository,
        local_phonebook: LocalPhonebookRepository,
    ) -> None:
        self._contacts = contacts
        self._phonebook = phonebook
        self._local_phonebook = local_phonebook

    @classmethod
    def for_connection(cls, connection: sqlite3.Connection) -> CallerDirectory:
        """Directory über die drei Repositories einer Connection."""
        return cls(
            ContactRepository(connection),
            PhonebookRepository(connection),
            LocalPhonebookRepository(connection),
        )

    def identify(self, raw_number: str | None) -> CallerIdentity:
        """Read-only: legt nie einen Caller an."""
        return self.identify_many([raw_number])[raw_number]

    def register(self, raw_number: str | None) -> CallerIdentity:
        """Wie identify, legt den Caller aber an, falls er fehlt (idempotent).

        Unterdrückte Nummern teilen sich - wie beim Sync - einen anonymen Pseudo-Caller."""
        identity = self.identify(raw_number)
        if identity.caller_id is not None:
            return identity
        caller_id = self._contacts.upsert(identity.number, is_anonymous=identity.is_anonymous)
        return CallerIdentity(
            identity.number, identity.is_anonymous, identity.name, identity.notes, caller_id
        )

    def identify_many(self, raw_numbers: list[str | None]) -> dict[str | None, CallerIdentity]:
        """Batched (konstant viele Queries); Schlüssel sind die rohen Eingaben."""
        normalized = {raw: normalize_number(raw) for raw in raw_numbers}
        real_numbers = sorted({n for n, anon in normalized.values() if not anon})
        all_numbers = sorted({n for n, _ in normalized.values()})
        local = self._local_phonebook.all_entries() if real_numbers else {}
        box = self._phonebook.all_names() if real_numbers else {}
        ids = self._contacts.ids_for_numbers(all_numbers) if all_numbers else {}
        result: dict[str | None, CallerIdentity] = {}
        for raw, (number, is_anonymous) in normalized.items():
            if is_anonymous:
                result[raw] = CallerIdentity(number, True, None, None, ids.get(number))
                continue
            notes = local.get(number, (None, None))[1]
            result[raw] = CallerIdentity(
                number, False, _resolve_name(number, local, box), notes, ids.get(number)
            )
        return result

    def refresh_names(self) -> int:
        """Schreibt contacts.display_name neu (einzige Schreibstelle), in einer Transaktion.

        Das Ergebnis ist maßgeblich: Löst eine Nummer nicht mehr auf, wird der Name
        geleert. Gibt die Anzahl geänderter Namen zurück."""
        local = self._local_phonebook.all_entries()
        box = self._phonebook.all_names()
        updates: dict[int, str | None] = {}
        for contact in self._contacts.search(""):
            name = _resolve_name(contact.primary_number, local, box)
            if name != contact.display_name:
                updates[contact.id] = name
        self._contacts.set_display_names(updates)
        return len(updates)

    @staticmethod
    def matches(query: str, identity: CallerIdentity) -> bool:
        """Trifft query den Namen (case-insensitiv) oder die Nummer (wie die SQL-Suche)?"""
        if identity.name and query.lower() in identity.name.lower():
            return True
        return any(s in identity.number for s in number_search_spellings(query))


def _resolve_name(
    number: str, local: dict[str, tuple[str | None, str | None]], box: dict[str, str]
) -> str | None:
    """Namensvorrang an einer Stelle: Telefonbuch-Kontakt, dann Box-Telefonbuch."""
    local_name = local.get(number, (None, None))[0]
    return local_name or box.get(number)
