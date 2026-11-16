"""Telefonbuch: der eine Schreibweg ins lokale, vom Nutzer gepflegte Telefonbuch.

Arbeitet mit Kontakt-Werten (ContactDraft/NumberDraft) und besitzt Normalisierung,
Dedupe, die Standardnummer-Regel und beide Import-Richtlinien (Import-Duplikat bei
Datei-Import, Adoptieren beim Box-Import). Kennt keine fritz/-Typen; die Box-Anbindung
(sync/box_gateway.py) wandelt Box-Kontakte in ContactDrafts um.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from fritz_callhistory.db.repository import LocalPhonebookContact, LocalPhonebookRepository
from fritz_callhistory.sync.normalize import normalize_number

if TYPE_CHECKING:
    from fritz_callhistory.sync.phonebook_io import ImportResult


@dataclass(frozen=True)
class NumberDraft:
    raw: str
    type: str
    is_default: bool = False


@dataclass
class ContactDraft:
    display_name: str
    notes: str | None
    numbers: list[NumberDraft] = field(default_factory=list)
    box_uniqueid: str | None = None


@dataclass
class ImportSummary:
    created: int
    skipped_duplicate: int
    warnings: list[str]


# Zeilenform des Repositorys: (raw, normalized, type, is_default)
_Row = tuple[str, str, str, bool]


def _clean_numbers(numbers: list[NumberDraft]) -> list[_Row]:
    """Normalisiert, verwirft anonyme/nicht erkennbare Nummern und Doppelte (erste
    gewinnt, inkl. is_default); höchstens eine Standardnummer (die erste markierte)."""
    rows: list[_Row] = []
    seen: set[str] = set()
    default_taken = False
    for number in numbers:
        normalized, is_anonymous = normalize_number(number.raw)
        if is_anonymous or normalized in seen:
            continue
        seen.add(normalized)
        is_default = number.is_default and not default_taken
        default_taken = default_taken or is_default
        rows.append((number.raw, normalized, number.type, is_default))
    return rows


class Telefonbuch:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection
        self._repo = LocalPhonebookRepository(connection)

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        """Alles oder nichts: Commit am Ende, bei jeder Ausnahme Rollback."""
        try:
            yield
        except BaseException:
            self._conn.rollback()
            raise
        self._conn.commit()

    # --- Lesen ---

    def list(self, query: str = "") -> list[LocalPhonebookContact]:
        return self._repo.list_all(query)

    def all_contacts(self) -> list[LocalPhonebookContact]:
        """Alle Kontakte, z.B. für den Export."""
        return self._repo.list_all()

    def get(self, contact_id: int) -> LocalPhonebookContact | None:
        return self._repo.get(contact_id)

    def find_by_number(self, raw_number: str) -> LocalPhonebookContact | None:
        """Kontakt, dem die Nummer gehört; None für anonyme/nicht erkennbare Nummern."""
        normalized, is_anonymous = normalize_number(raw_number)
        if is_anonymous:
            return None
        return self._repo.find_by_number(normalized)

    # --- Schreiben ---

    def create(self, draft: ContactDraft) -> int:
        with self._transaction():
            return self._create(draft)

    def update(self, contact_id: int, draft: ContactDraft) -> None:
        with self._transaction():
            self._repo.update(
                contact_id,
                display_name=draft.display_name,
                notes=draft.notes,
                numbers=_clean_numbers(draft.numbers),
                commit=False,
            )

    def delete(self, contact_id: int) -> None:
        with self._transaction():
            self._repo.delete(contact_id, commit=False)

    def _create(self, draft: ContactDraft, rows: list[_Row] | None = None) -> int:
        return self._repo.create(
            display_name=draft.display_name,
            notes=draft.notes,
            numbers=_clean_numbers(draft.numbers) if rows is None else rows,
            box_uniqueid=draft.box_uniqueid,
            commit=False,
        )

    # --- Importe (je ein Aufruf = eine Transaktion) ---

    def import_file(self, result: ImportResult) -> ImportSummary:
        """Legt neue Kontakte an; überspringt Import-Duplikate.

        Import-Duplikat: die komplette (nicht-leere) Nummernmenge des Kontakts ist
        exakt die Nummernmenge eines bestehenden Telefonbuch-Kontakts. Macht
        wiederholtes Importieren derselben Datei idempotent (zweiter Lauf:
        created=0, skipped_duplicate=N); kein Fuzzy-Merge.
        """
        created = 0
        skipped = 0
        with self._transaction():
            for draft in result.contacts:
                rows = _clean_numbers(draft.numbers)
                if rows and self._repo.find_ids_by_exact_numbers({r[1] for r in rows}):
                    skipped += 1
                    continue
                self._create(draft, rows)
                created += 1
        return ImportSummary(created, skipped, list(result.warnings))

    def import_box_contacts(self, drafts: list[ContactDraft]) -> int:
        """Übernimmt Box-Kontakte (Drafts mit box_uniqueid) ins Telefonbuch.

        Pro Draft mit Namen: existiert ein Kontakt mit derselben Box-Id, wird er
        aktualisiert (Notizen bleiben, die Standardnummer bleibt, solange sie noch
        auf der Box steht); sonst wird ein Kontakt ohne Box-Id mit exakt derselben
        Nummernmenge adoptiert (mit der Box-Id verknüpft); sonst neu angelegt. Die
        Zuordnungsregel unterscheidet sich bewusst vom Import-Duplikat in
        import_file(). Gibt die Anzahl verarbeiteter Drafts zurück.
        """
        processed = 0
        with self._transaction():
            for draft in drafts:
                if not draft.display_name:
                    continue
                rows = _clean_numbers(draft.numbers)
                existing = (
                    self._repo.find_by_box_uniqueid(draft.box_uniqueid)
                    if draft.box_uniqueid
                    else None
                )
                if existing:
                    # Die Box kennt keine Standardnummer: lokal gesetzte bleibt erhalten.
                    defaults = {n.number_normalized for n in existing.numbers if n.is_default}
                    self._repo.update(
                        existing.id,
                        display_name=draft.display_name,
                        notes=existing.notes,
                        numbers=[(r, n, t, n in defaults) for r, n, t, _ in rows],
                        commit=False,
                    )
                else:
                    adoptable = (
                        self._repo.find_ids_by_exact_numbers(
                            {r[1] for r in rows}, without_box_uniqueid=True
                        )
                        if draft.box_uniqueid
                        else []
                    )
                    if adoptable:
                        self._repo.set_box_uniqueid(adoptable[0], draft.box_uniqueid, commit=False)
                    else:
                        self._create(draft, rows)
                processed += 1
        return processed
