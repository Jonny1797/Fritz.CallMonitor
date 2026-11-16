import os
import sqlite3

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from fritz_callhistory.db.schema import migrate


@pytest.fixture
def connection():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    migrate(conn)
    yield conn
    conn.close()


@pytest.fixture(autouse=True)
def _no_real_call_monitor(mocker):
    """MainWindow startet den CallMonitor, sobald die Config eine Adresse hat - in Tests
    darf dabei keine echte Verbindung aufgebaut werden (Tests können erneut patchen)."""
    mocker.patch("fritz_callhistory.gui.main_window.CallMonitorThread")
