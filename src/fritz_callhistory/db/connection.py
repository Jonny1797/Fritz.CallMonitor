"""Connection-Factory für die SQLite-Datenbank."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fritz_callhistory.db.schema import migrate


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Öffnet (und legt bei Bedarf an) die SQLite-Datenbank und wendet Migrationen an."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    migrate(connection)
    return connection
