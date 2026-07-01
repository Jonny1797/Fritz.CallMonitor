# fritz-callhistory

Desktop-App (PySide6) für die AVM Fritz!Box: durchsuchbare Anrufliste (Name/Nummer)
und letzte Interaktionen pro Kontakt. Synchronisiert die Anrufliste der Box in eine
lokale SQLite-Datenbank, damit die Historie über die von der Box gehaltene Grenze
hinaus erhalten bleibt.

## Setup

```bash
uv sync
```

## Verbindung testen

```bash
FRITZ_ADDRESS=192.168.178.1 FRITZ_USER=<benutzername> uv run python scripts/check_connection.py
```

Fragt bei Bedarf interaktiv nach dem Passwort (nicht als Umgebungsvariable ablegen).

Voraussetzungen auf der Box:
- Heimnetz > Netzwerk > Netzwerkeinstellungen > "Zugriff für Anwendungen zulässig" aktiviert.
- Der verwendete Benutzer hat das Recht "Sprachnachrichten, Fax, Anrufliste und FRITZ!App Fon".

## App starten

```bash
uv run fritz-callhistory
```

## Tests

```bash
uv run pytest
```

## Windows-.exe bauen (PyInstaller)

```bash
uv run pyinstaller packaging/fritz_callhistory.spec
```

Ergebnis: eine einzelne `dist/fritz-callhistory(.exe)` (onefile, kein Konsolenfenster).
Die Fritz!Box-Zugangsdaten werden beim ersten Start über einen Dialog abgefragt und
im OS-Schlüsselbund gespeichert - nicht Teil der .exe.
