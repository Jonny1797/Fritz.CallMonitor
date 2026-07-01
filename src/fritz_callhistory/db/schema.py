"""Migrationslogik über PRAGMA user_version + nummerierte SQL-Dateien."""

from __future__ import annotations

import re
import sqlite3
from importlib import resources

_MIGRATION_PATTERN = re.compile(r"^(\d+)_.*\.sql$")


def _migrations() -> list[tuple[int, str]]:
    migrations_dir = resources.files("fritz_callhistory.db") / "migrations"
    found = []
    for entry in migrations_dir.iterdir():
        match = _MIGRATION_PATTERN.match(entry.name)
        if match:
            found.append((int(match.group(1)), entry.read_text(encoding="utf-8")))
    return sorted(found, key=lambda item: item[0])


def migrate(connection: sqlite3.Connection) -> None:
    """Bringt die Datenbank auf den neuesten Schema-Stand (idempotent)."""
    current_version = connection.execute("PRAGMA user_version").fetchone()[0]
    for version, sql in _migrations():
        if version <= current_version:
            continue
        connection.executescript(sql)
        connection.execute(f"PRAGMA user_version = {version}")
    connection.commit()
