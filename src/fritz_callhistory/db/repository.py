"""Repository-Schicht: gekapselter SQL-Zugriff für Kontakte, Anrufe und Sync-Status.

Kein ORM (siehe Plan) - für die überschaubare Anzahl Tabellen reicht rohes SQL,
mit voller Kontrolle über die Such-Queries.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


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

    def get(self, contact_id: int) -> Contact | None:
        row = self._conn.execute(
            """
            SELECT c.id, c.primary_number, c.display_name, c.is_anonymous,
                   MAX(calls.call_date) AS last_call_date, COUNT(calls.id) AS call_count
            FROM contacts c
            LEFT JOIN calls ON calls.contact_id = c.id
            WHERE c.id = ?
            GROUP BY c.id
            """,
            (contact_id,),
        ).fetchone()
        return self._row_to_contact(row) if row else None

    def find_by_number(self, primary_number: str) -> Contact | None:
        row = self._conn.execute(
            """
            SELECT c.id, c.primary_number, c.display_name, c.is_anonymous,
                   MAX(calls.call_date) AS last_call_date, COUNT(calls.id) AS call_count
            FROM contacts c
            LEFT JOIN calls ON calls.contact_id = c.id
            WHERE c.primary_number = ?
            GROUP BY c.id
            """,
            (primary_number,),
        ).fetchone()
        return self._row_to_contact(row) if row else None

    def search(self, query: str = "") -> list[Contact]:
        pattern = f"%{query}%"
        rows = self._conn.execute(
            """
            SELECT c.id, c.primary_number, c.display_name, c.is_anonymous,
                   MAX(calls.call_date) AS last_call_date, COUNT(calls.id) AS call_count
            FROM contacts c
            LEFT JOIN calls ON calls.contact_id = c.id
            WHERE c.display_name LIKE ? OR c.primary_number LIKE ?
            GROUP BY c.id
            ORDER BY last_call_date DESC
            """,
            (pattern, pattern),
        ).fetchall()
        return [self._row_to_contact(row) for row in rows]

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
    ) -> bool:
        """Fügt einen Anruf ein. Gibt False zurück, wenn er bereits existiert (Dedupe)."""
        cursor = self._conn.execute(
            """
            INSERT OR IGNORE INTO calls (
                contact_id, call_type, caller_number, called_number,
                port, device, call_date, duration_seconds, raw_name
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            ),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def for_contact(self, contact_id: int, limit: int | None = None) -> list[CallRecord]:
        sql = "SELECT * FROM calls WHERE contact_id = ? ORDER BY call_date DESC"
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
    ) -> list[CallWithContact]:
        """Alle Anrufe ueber alle Kontakte hinweg, chronologisch, optional per
        ISO8601-Zeitstempel (inklusiv) und/oder call_type eingegrenzt."""
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
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        # Explizite Spaltenliste mit Aliassen statt calls.*/contacts.*: beide
        # Tabellen haben eine id-Spalte, was sonst bei sqlite3.Row-Zugriff per
        # Name mehrdeutig waere. INNER JOIN ist sicher, da sync/service.py fuer
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
                contacts.display_name AS contact_display_name,
                contacts.primary_number AS contact_primary_number,
                contacts.is_anonymous AS contact_is_anonymous
            FROM calls
            JOIN contacts ON contacts.id = calls.contact_id
            {where}
            ORDER BY calls.call_date DESC
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

    def lookup_name(self, number_normalized: str) -> str | None:
        row = self._conn.execute(
            "SELECT name FROM phonebook_entries WHERE number_normalized = ? ORDER BY phonebook_id LIMIT 1",
            (number_normalized,),
        ).fetchone()
        return row["name"] if row else None


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
