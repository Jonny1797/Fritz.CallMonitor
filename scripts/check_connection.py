"""Isolierter Verbindungstest gegen die Fritz!Box, ohne DB/GUI.

Nutzung:
    FRITZ_ADDRESS=192.168.178.1 FRITZ_USER=<benutzername> uv run python scripts/check_connection.py

Das Passwort wird interaktiv abgefragt (nicht als Umgebungsvariable ablegen).
"""

from __future__ import annotations

import getpass
import os
import sys

from fritzconnection import FritzConnection
from fritzconnection.core.exceptions import FritzConnectionException
from fritzconnection.lib.fritzcall import FritzCall


def main() -> int:
    address = os.environ.get("FRITZ_ADDRESS", "192.168.178.1")
    user = os.environ.get("FRITZ_USER")
    if not user:
        print("FRITZ_USER Umgebungsvariable fehlt.", file=sys.stderr)
        return 1
    password = os.environ.get("FRITZ_PASSWORD") or getpass.getpass(
        f"Fritz!Box-Passwort für {user}@{address}: "
    )

    try:
        fc = FritzConnection(address=address, user=user, password=password)
    except FritzConnectionException as exc:
        print(f"Verbindung/Login fehlgeschlagen: {exc}", file=sys.stderr)
        return 1

    print(f"Verbunden mit: {fc.modelname} (FRITZ!OS {fc.system_version})")

    try:
        calls = FritzCall(fc).get_calls(num=5)
    except FritzConnectionException as exc:
        print(
            "Anrufliste konnte nicht gelesen werden - hat der Benutzer das Recht "
            "'Sprachnachrichten, Fax, Anrufliste und FRITZ!App Fon'?",
            file=sys.stderr,
        )
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1

    if not calls:
        print("Keine Anrufe in der Liste gefunden (leer, aber Zugriff funktioniert).")
        return 0

    print(f"\nLetzte {len(calls)} Anrufe:")
    for call in calls:
        print(f"  {call}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
