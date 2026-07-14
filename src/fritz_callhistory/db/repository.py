"""Repository-Schicht: gekapselter SQL-Zugriff für Kontakte, Anrufe und Sync-Status.

Kein ORM (siehe Plan) - für die überschaubare Anzahl Tabellen reicht rohes SQL,
mit voller Kontrolle über die Such-Queries.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime

_NUMBER_SEARCH_SEPARATORS = str.maketrans("", "", " -()/")
_NUMBER_SEARCH_PATTERN = re.compile(r"\+?[0-9]+")


def _number_search_patterns(query: str) -> list[str]:
    """Zusätzliche LIKE-Muster, damit z.B. "0176" auch in E.164-normalisierten
    Nummern wie "+49176123456" gefunden wird - die DB speichert stets E.164,
    aber ein Suchfeld bekommt naheliegenderweise oft die Nummer in nationaler
    (oder international mit führenden Nullen statt "+") Schreibweise."""
    patterns = [f"%{query}%"]
    cleaned = query.translate(_NUMBER_SEARCH_SEPARATORS)
    if not _NUMBER_SEARCH_PATTERN.fullmatch(cleaned or ""):
        return patterns
    if cleaned.startswith("00") and len(cleaned) > 4:
        patterns.append(f"%+{cleaned[2:]}%")
    elif cleaned.startswith("0") and len(cleaned) > 3:
        patterns.append(f"%+49{cleaned[1:]}%")
    return patterns


@dataclass
class Contact:
    id: int
    primary_number: str
    display_name: str | None
    is_anonymous: bool
    last_call_date: str | None
    call_count: int


@dataclass
class CallRecord:
    id: int
    contact_id: int
    call_type: int
    caller_number: str | None
    called_number: str | None
    port: str | None
    device: str | None
    call_date: str
    duration_seconds: int | None
    raw_name: str | None
    box_call_id: int | None = None


@dataclass
class CallWithContact:
    id: int
    contact_id: int
    call_type: int
    caller_number: str | None
    called_number: str | None
    port: str | None
    device: str | None
    call_date: str
    duration_seconds: int | None
    raw_name: str | None
    contact_display_name: str | None
    contact_primary_number: str
    contact_is_anonymous: bool
    box_call_id: int | None = None


class ContactRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection

    def upsert(self, primary_number: str, *, is_anonymous: bool = False) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO contacts (primary_number, is_anonymous)
            VALUES (?, ?)
            ON CONFLICT (primary_number) DO UPDATE SET primary_number = excluded.primary_number
            RETURNING id
            """,
            (primary_number, int(is_anonymous)),
        )
        contact_id = cursor.fetchone()[0]
        self._conn.commit()
        return contact_id

    def set_display_name(self, contact_id: int, display_name: str | None) -> None:
        self._conn.execute(
            "UPDATE contacts SET display_name = ? WHERE id = ?",
            (display_name, contact_id),
        )
        self._conn.commit()

    def set_display_names(self, updates: dict[int, str]) -> None:
        """Batched Variante von set_display_name für viele Kontakte in einer Transaktion."""
        if not updates:
            return
        self._conn.executemany(
            "UPDATE contacts SET display_name = ? WHERE id = ?",
            [(name, contact_id) for contact_id, name in updates.items()],
        )
        self._conn.commit()

    def _query(self, where: str, params: tuple, order_by: str = "") -> list[Contact]:
        rows = self._conn.execute(
            f"""
            SELECT c.id, c.primary_number, c.display_name, c.is_anonymous,
                   MAX(calls.call_date) AS last_call_date, COUNT(calls.id) AS call_count
            FROM contacts c
            LEFT JOIN calls ON calls.contact_id = c.id
            WHERE {where}
            GROUP BY c.id
            {order_by}
            """,
            params,
        ).fetchall()
        return [self._row_to_contact(row) for row in rows]

    def get(self, contact_id: int) -> Contact | None:
        # c.id ist Primary Key: WHERE liefert höchstens eine Zeile.
        rows = self._query("c.id = ?", (contact_id,))
        return rows[0] if rows else None

    def find_by_number(self, primary_number: str) -> Contact | None:
        # primary_number ist UNIQUE: WHERE liefert höchstens eine Zeile.
        rows = self._query("c.primary_number = ?", (primary_number,))
        return rows[0] if rows else None

    def search(self, query: str = "") -> list[Contact]:
        name_pattern = f"%{query}%"
        number_patterns = _number_search_patterns(query)
        where = "(c.display_name LIKE ? OR {})".format(
            " OR ".join(["c.primary_number LIKE ?"] * len(number_patterns))
        )
        return self._query(
            where,
            (name_pattern, *number_patterns),
            order_by="ORDER BY last_call_date DESC",
        )

    @staticmethod
    def _row_to_contact(row: sqlite3.Row) -> Contact:
        return Contact(
            id=row["id"],
            primary_number=row["primary_number"],
            display_name=row["display_name"],
            is_anonymous=bool(row["is_anonymous"]),
            last_call_date=row["last_call_date"],
            call_count=row["call_count"],
        )


class CallRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection

    def insert(
        self,
        *,
        contact_id: int,
        call_type: int,
        caller_number: str | None,
        called_number: str | None,
        port: str | None,
        device: str | None,
        call_date: str,
        duration_seconds: int | None,
        raw_name: str | None,
        box_call_id: int | None = None,
    ) -> bool:
        """Fügt einen Anruf ein. Gibt False zurück, wenn er bereits existiert (Dedupe).

        box_call_id ist die von der Box vergebene Id (für die Sortierung bei
        exakt gleichem call_date - der Zeitstempel selbst hat nur Minuten-
        genauigkeit, siehe db/migrations/002_add_box_call_id.sql). Bewusst
        NICHT Teil des Dedupe-Schlüssels, da diese Id über lange Zeiträume
        rotiert und daher nicht global stabil ist.
        """
        cursor = self._conn.execute(
            """
            INSERT OR IGNORE INTO calls (
                contact_id, call_type, caller_number, called_number,
                port, device, call_date, duration_seconds, raw_name, box_call_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                contact_id,
                call_type,
                caller_number,
                called_number,
                port,
                device,
                call_date,
                duration_seconds,
                raw_name,
                box_call_id,
            ),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def for_contact(self, contact_id: int, limit: int | None = None) -> list[CallRecord]:
        sql = (
            "SELECT * FROM calls WHERE contact_id = ? "
            "ORDER BY call_date DESC, box_call_id DESC"
        )
        params: tuple = (contact_id,)
        if limit is not None:
            sql += " LIMIT ?"
            params = (contact_id, limit)
        rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_call(row) for row in rows]

    def all_calls(
        self,
        *,
        date_from: str | None = None,
        date_to: str | None = None,
        call_types: list[int] | None = None,
        search: str = "",
    ) -> list[CallWithContact]:
        """Alle Anrufe über alle Kontakte hinweg, chronologisch, optional per
        ISO8601-Zeitstempel (inklusiv), call_type und/oder Name/Nummer eingegrenzt."""
        conditions = []
        params: list = []
        if date_from is not None:
            conditions.append("calls.call_date >= ?")
            params.append(date_from)
        if date_to is not None:
            conditions.append("calls.call_date <= ?")
            params.append(date_to)
        if call_types:
            placeholders = ",".join("?" * len(call_types))
            conditions.append(f"calls.call_type IN ({placeholders})")
            params.extend(call_types)
        if search:
            # Geklammert, da sonst ein unparenthesiertes OR aus den anderen
            # (per AND verknüpften) Bedingungen ausbrechen würde.
            number_patterns = _number_search_patterns(search)
            conditions.append(
                "(contacts.display_name LIKE ? OR {})".format(
                    " OR ".join(["contacts.primary_number LIKE ?"] * len(number_patterns))
                )
            )
            params.append(f"%{search}%")
            params.extend(number_patterns)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        # Explizite Spaltenliste mit Aliassen statt calls.*/contacts.*: beide
        # Tabellen haben eine id-Spalte, was sonst bei sqlite3.Row-Zugriff per
        # Name mehrdeutig wäre. INNER JOIN ist sicher, da sync/service.py für
        # jeden Call vorher immer ContactRepository.upsert() aufruft.
        rows = self._conn.execute(
            f"""
            SELECT
                calls.id AS id,
                calls.contact_id AS contact_id,
                calls.call_type AS call_type,
                calls.caller_number AS caller_number,
                calls.called_number AS called_number,
                calls.port AS port,
                calls.device AS device,
                calls.call_date AS call_date,
                calls.duration_seconds AS duration_seconds,
                calls.raw_name AS raw_name,
                calls.box_call_id AS box_call_id,
                contacts.display_name AS contact_display_name,
                contacts.primary_number AS contact_primary_number,
                contacts.is_anonymous AS contact_is_anonymous
            FROM calls
            JOIN contacts ON contacts.id = calls.contact_id
            {where}
            ORDER BY calls.call_date DESC, calls.box_call_id DESC
            """,
            params,
        ).fetchall()
        return [self._row_to_call_with_contact(row) for row in rows]

    @staticmethod
    def _row_to_call(row: sqlite3.Row) -> CallRecord:
        return CallRecord(
            id=row["id"],
            contact_id=row["contact_id"],
            call_type=row["call_type"],
            caller_number=row["caller_number"],
            called_number=row["called_number"],
            port=row["port"],
            device=row["device"],
            call_date=row["call_date"],
            duration_seconds=row["duration_seconds"],
            raw_name=row["raw_name"],
            box_call_id=row["box_call_id"],
        )

    @staticmethod
    def _row_to_call_with_contact(row: sqlite3.Row) -> CallWithContact:
        return CallWithContact(
            id=row["id"],
            contact_id=row["contact_id"],
            call_type=row["call_type"],
            caller_number=row["caller_number"],
            called_number=row["called_number"],
            port=row["port"],
            device=row["device"],
            call_date=row["call_date"],
            duration_seconds=row["duration_seconds"],
            raw_name=row["raw_name"],
            contact_display_name=row["contact_display_name"],
            contact_primary_number=row["contact_primary_number"],
            contact_is_anonymous=bool(row["contact_is_anonymous"]),
            box_call_id=row["box_call_id"],
        )


class PhonebookRepository:
    """Cache der Fritz!Box-Telefonbücher (Rufnummer -> Name) für die Namensauflösung."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection

    def replace_entries(self, phonebook_id: int, entries: list[tuple[str, str]]) -> None:
        """Ersetzt den kompletten Cache für dieses Telefonbuch.

        entries: Liste von (name, number_normalized).
        """
        self._conn.execute("DELETE FROM phonebook_entries WHERE phonebook_id = ?", (phonebook_id,))
        self._conn.executemany(
            "INSERT INTO phonebook_entries (phonebook_id, name, number_normalized) VALUES (?, ?, ?)",
            [(phonebook_id, name, number) for name, number in entries],
        )
        self._conn.commit()

    def all_names(self) -> dict[str, str]:
        """number_normalized -> name für alle Einträge. Bei mehreren Telefonbüchern mit
        derselben Nummer gewinnt die niedrigste phonebook_id (ORDER BY ASC + first-wins
        via setdefault) - dieselbe Priorität, die die frühere lookup_name-Einzelabfrage
        per ORDER BY phonebook_id LIMIT 1 pro Nummer hatte."""
        names: dict[str, str] = {}
        rows = self._conn.execute(
            "SELECT number_normalized, name FROM phonebook_entries ORDER BY phonebook_id"
        ).fetchall()
        for row in rows:
            names.setdefault(row["number_normalized"], row["name"])
        return names


@dataclass
class PhonebookNumber:
    id: int
    number_raw: str
    number_normalized: str
    number_type: str
    is_default: bool


@dataclass
class LocalPhonebookContact:
    id: int
    display_name: str
    notes: str | None
    box_uniqueid: str | None
    numbers: list[PhonebookNumber]


class LocalPhonebookRepository:
    """Lokales, vom Nutzer gepflegtes Telefonbuch (mehrere Nummern pro Kontakt).

    Im Unterschied zu PhonebookRepository (Wipe-and-Rewrite-Cache der
    Box-Telefonbücher) ist dies hier die Quelle der Wahrheit für den Nutzer.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection

    def list_all(self, query: str = "") -> list[LocalPhonebookContact]:
        pattern = f"%{query}%"
        rows = self._conn.execute(
            "SELECT id FROM phonebook_contacts WHERE display_name LIKE ? ORDER BY display_name",
            (pattern,),
        ).fetchall()
        return [self._load(row["id"]) for row in rows]

    def get(self, contact_id: int) -> LocalPhonebookContact | None:
        row = self._conn.execute(
            "SELECT id FROM phonebook_contacts WHERE id = ?", (contact_id,)
        ).fetchone()
        return self._load(row["id"]) if row else None

    def create(
        self,
        *,
        display_name: str,
        notes: str | None,
        numbers: list[tuple[str, str, str, bool]],
        box_uniqueid: str | None = None,
    ) -> int:
        """numbers: Liste von (number_raw, number_normalized, number_type, is_default)."""
        now = datetime.now().isoformat()
        cursor = self._conn.execute(
            """
            INSERT INTO phonebook_contacts (display_name, notes, box_uniqueid, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (display_name, notes, box_uniqueid, now, now),
        )
        contact_id = cursor.lastrowid
        self._insert_numbers(contact_id, numbers)
        self._conn.commit()
        return contact_id

    def update(
        self,
        contact_id: int,
        *,
        display_name: str,
        notes: str | None,
        numbers: list[tuple[str, str, str, bool]],
    ) -> None:
        now = datetime.now().isoformat()
        self._conn.execute(
            "UPDATE phonebook_contacts SET display_name = ?, notes = ?, updated_at = ? WHERE id = ?",
            (display_name, notes, now, contact_id),
        )
        self._conn.execute(
            "DELETE FROM phonebook_contact_numbers WHERE phonebook_contact_id = ?", (contact_id,)
        )
        self._insert_numbers(contact_id, numbers)
        self._conn.commit()

    def delete(self, contact_id: int) -> None:
        self._conn.execute("DELETE FROM phonebook_contacts WHERE id = ?", (contact_id,))
        self._conn.commit()

    def lookup_name(self, number_normalized: str) -> str | None:
        row = self._conn.execute(
            """
            SELECT pc.display_name AS display_name
            FROM phonebook_contact_numbers pcn
            JOIN phonebook_contacts pc ON pc.id = pcn.phonebook_contact_id
            WHERE pcn.number_normalized = ?
            ORDER BY pc.id LIMIT 1
            """,
            (number_normalized,),
        ).fetchone()
        return row["display_name"] if row else None

    def all_names(self) -> dict[str, str]:
        """number_normalized -> display_name für alle Kontakte. Bei mehreren Kontakten mit
        derselben Nummer gewinnt die niedrigste phonebook_contact_id - dieselbe Priorität,
        die die frühere lookup_name-Einzelabfrage per ORDER BY pc.id LIMIT 1 pro Nummer hatte."""
        names: dict[str, str] = {}
        rows = self._conn.execute(
            """
            SELECT pcn.number_normalized AS number_normalized, pc.display_name AS display_name
            FROM phonebook_contact_numbers pcn
            JOIN phonebook_contacts pc ON pc.id = pcn.phonebook_contact_id
            ORDER BY pc.id
            """
        ).fetchall()
        for row in rows:
            names.setdefault(row["number_normalized"], row["display_name"])
        return names

    def find_by_number(self, number_normalized: str) -> LocalPhonebookContact | None:
        """Wie lookup_name, aber gibt den vollen Kontakt zurück - für den
        Doppelklick-auf-Nummer-Einstiegspunkt (gui/phonebook_view.py's
        add_or_edit_number), der entscheiden muss, ob bearbeitet oder neu
        angelegt wird."""
        row = self._conn.execute(
            """
            SELECT pc.id AS id
            FROM phonebook_contact_numbers pcn
            JOIN phonebook_contacts pc ON pc.id = pcn.phonebook_contact_id
            WHERE pcn.number_normalized = ?
            ORDER BY pc.id LIMIT 1
            """,
            (number_normalized,),
        ).fetchone()
        return self._load(row["id"]) if row else None

    def find_by_box_uniqueid(self, box_uniqueid: str) -> LocalPhonebookContact | None:
        row = self._conn.execute(
            "SELECT id FROM phonebook_contacts WHERE box_uniqueid = ?", (box_uniqueid,)
        ).fetchone()
        return self._load(row["id"]) if row else None

    def set_box_uniqueid(self, contact_id: int, box_uniqueid: str) -> None:
        self._conn.execute(
            "UPDATE phonebook_contacts SET box_uniqueid = ? WHERE id = ?",
            (box_uniqueid, contact_id),
        )
        self._conn.commit()

    def all_numbers_belong_to_one_contact(self, numbers_normalized: list[str]) -> bool:
        """True, wenn jede angegebene Nummer zu genau demselben bestehenden
        Kontakt gehört und dieser exakt diese Nummernmenge hat - für
        Idempotenz beim wiederholten Datei-Import (siehe sync/phonebook_io.py)."""
        if not numbers_normalized:
            return False
        contact_ids: set[int] = set()
        for number in numbers_normalized:
            rows = self._conn.execute(
                "SELECT phonebook_contact_id FROM phonebook_contact_numbers WHERE number_normalized = ?",
                (number,),
            ).fetchall()
            ids = {row["phonebook_contact_id"] for row in rows}
            if not ids:
                return False
            contact_ids |= ids
        if len(contact_ids) != 1:
            return False
        return self._numbers_of(next(iter(contact_ids))) == set(numbers_normalized)

    def find_local_only_contact_by_exact_numbers(self, numbers_normalized: list[str]) -> int | None:
        """Wie all_numbers_belong_to_one_contact, aber nur unter Kontakten ohne
        box_uniqueid - die "Adoptieren"-Heuristik beim Box-Import: ein zuvor
        lokal angelegter Kontakt wird mit dem passenden Box-Eintrag verknüpft,
        statt dupliziert zu werden (siehe app.py's _build_import_from_box_fn)."""
        if not numbers_normalized:
            return None
        rows = self._conn.execute(
            """
            SELECT DISTINCT pcn.phonebook_contact_id AS id
            FROM phonebook_contact_numbers pcn
            JOIN phonebook_contacts pc ON pc.id = pcn.phonebook_contact_id
            WHERE pcn.number_normalized = ? AND pc.box_uniqueid IS NULL
            """,
            (numbers_normalized[0],),
        ).fetchall()
        for row in rows:
            contact_id = row["id"]
            if self._numbers_of(contact_id) == set(numbers_normalized):
                return contact_id
        return None

    def _numbers_of(self, contact_id: int) -> set[str]:
        return {
            row["number_normalized"]
            for row in self._conn.execute(
                "SELECT number_normalized FROM phonebook_contact_numbers WHERE phonebook_contact_id = ?",
                (contact_id,),
            ).fetchall()
        }

    def _insert_numbers(self, contact_id: int, numbers: list[tuple[str, str, str, bool]]) -> None:
        self._conn.executemany(
            """
            INSERT INTO phonebook_contact_numbers
                (phonebook_contact_id, number_raw, number_normalized, number_type, is_default)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (contact_id, raw, normalized, number_type, int(is_default))
                for raw, normalized, number_type, is_default in numbers
            ],
        )

    def _load(self, contact_id: int) -> LocalPhonebookContact:
        contact_row = self._conn.execute(
            "SELECT id, display_name, notes, box_uniqueid FROM phonebook_contacts WHERE id = ?",
            (contact_id,),
        ).fetchone()
        number_rows = self._conn.execute(
            "SELECT id, number_raw, number_normalized, number_type, is_default "
            "FROM phonebook_contact_numbers WHERE phonebook_contact_id = ? ORDER BY id",
            (contact_id,),
        ).fetchall()
        return LocalPhonebookContact(
            id=contact_row["id"],
            display_name=contact_row["display_name"],
            notes=contact_row["notes"],
            box_uniqueid=contact_row["box_uniqueid"],
            numbers=[
                PhonebookNumber(
                    id=row["id"],
                    number_raw=row["number_raw"],
                    number_normalized=row["number_normalized"],
                    number_type=row["number_type"],
                    is_default=bool(row["is_default"]),
                )
                for row in number_rows
            ],
        )


class SyncStateRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection

    def get(self, key: str, default: str | None = None) -> str | None:
        row = self._conn.execute(
            "SELECT value FROM sync_state WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default

    def set(self, key: str, value: str) -> None:
        self._conn.execute(
            """
            INSERT INTO sync_state (key, value) VALUES (?, ?)
            ON CONFLICT (key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        self._conn.commit()


@dataclass
class VoicemailMessageRecord:
    id: int
    tam_index: int
    box_path: str
    caller_number: str | None
    called_number: str | None
    message_date: str
    duration_seconds: int | None
    raw_name: str | None
    is_new: bool


class VoicemailRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection

    def insert_or_update(
        self,
        *,
        tam_index: int,
        box_path: str,
        caller_number: str | None,
        called_number: str | None,
        message_date: str,
        duration_seconds: int | None,
        raw_name: str | None,
        is_new: bool,
    ) -> bool:
        """Fügt eine Nachricht ein. Gibt False zurück, wenn sie bereits existiert (Dedupe).

        Anders als CallRepository.insert() aktualisiert ein Dedupe-Treffer zusätzlich
        is_new auf der bestehenden Zeile: die Box ist für "neu/gehört" allein
        maßgeblich (kann sich z.B. ändern, wenn die Nachricht an einem Telefon
        abgehört wurde) und muss bei jedem Sync aktualisierbar bleiben.
        """
        cursor = self._conn.execute(
            """
            INSERT OR IGNORE INTO voicemail_messages (
                tam_index, box_path, caller_number, called_number,
                message_date, duration_seconds, raw_name, is_new
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tam_index,
                box_path,
                caller_number,
                called_number,
                message_date,
                duration_seconds,
                raw_name,
                int(is_new),
            ),
        )
        was_inserted = cursor.rowcount > 0
        if not was_inserted:
            self._conn.execute(
                """
                UPDATE voicemail_messages SET is_new = ?
                WHERE tam_index = ? AND box_path = ? AND message_date = ?
                """,
                (int(is_new), tam_index, box_path, message_date),
            )
        self._conn.commit()
        return was_inserted

    def list_messages(self) -> list[VoicemailMessageRecord]:
        rows = self._conn.execute(
            "SELECT * FROM voicemail_messages ORDER BY message_date DESC"
        ).fetchall()
        return [self._row_to_message(row) for row in rows]

    def get(self, message_id: int) -> VoicemailMessageRecord | None:
        row = self._conn.execute(
            "SELECT * FROM voicemail_messages WHERE id = ?", (message_id,)
        ).fetchone()
        return self._row_to_message(row) if row else None

    def delete(self, message_id: int) -> None:
        self._conn.execute("DELETE FROM voicemail_messages WHERE id = ?", (message_id,))
        self._conn.commit()

    def mark_read_locally(self, message_id: int) -> None:
        """Setzt is_new lokal sofort auf 0, ohne auf den nächsten Sync zu warten -
        genutzt direkt nach einem erfolgreichen MarkMessage-Aufruf auf der Box
        (Abspielen oder der explizite "Gelesen"-Button), damit die rot/fett-Markierung
        sofort verschwindet statt erst beim nächsten Sync."""
        self._conn.execute(
            "UPDATE voicemail_messages SET is_new = 0 WHERE id = ?", (message_id,)
        )
        self._conn.commit()

    def prune_missing(
        self, existing_keys: set[tuple[int, str, str]], queried_tam_indices: set[int]
    ) -> None:
        """Entfernt lokale Nachrichten, die beim letzten vollständigen Sync nicht
        mehr unter den Box-Nachrichten waren (z.B. an einem Telefon gelöscht) -
        existing_keys ist die Menge aller (tam_index, box_path, message_date) der
        Nachrichten, die der letzte Sync tatsächlich von der Box zurückbekommen hat.

        Pruning bleibt auf queried_tam_indices beschränkt (die TAM-Slots, die dieser
        Sync tatsächlich abgefragt hat): fällt ein Slot vorübergehend aus
        voicemail_tam_indices() heraus (z.B. ein GetList-Hickup oder der Nutzer
        deaktiviert ihn kurz), sollen dessen bereits synchronisierte Nachrichten nicht
        fälschlich als "auf der Box gelöscht" verschwinden."""
        rows = self._conn.execute(
            "SELECT id, tam_index, box_path, message_date FROM voicemail_messages"
        ).fetchall()
        stale_ids = [
            row["id"]
            for row in rows
            if row["tam_index"] in queried_tam_indices
            and (row["tam_index"], row["box_path"], row["message_date"]) not in existing_keys
        ]
        if stale_ids:
            self._conn.executemany(
                "DELETE FROM voicemail_messages WHERE id = ?",
                [(message_id,) for message_id in stale_ids],
            )
            self._conn.commit()

    @staticmethod
    def _row_to_message(row: sqlite3.Row) -> VoicemailMessageRecord:
        return VoicemailMessageRecord(
            id=row["id"],
            tam_index=row["tam_index"],
            box_path=row["box_path"],
            caller_number=row["caller_number"],
            called_number=row["called_number"],
            message_date=row["message_date"],
            duration_seconds=row["duration_seconds"],
            raw_name=row["raw_name"],
            is_new=bool(row["is_new"]),
        )
