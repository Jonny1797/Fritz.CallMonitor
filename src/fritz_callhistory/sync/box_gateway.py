"""Box-Gateway: der eine Weg der App, mit den gespeicherten Zugangsdaten auf die
Fritz!Box zuzugreifen (Sync, Wählen, Box-Import, Anrufbeantworter, Zugangsdaten-Check).

Kein Qt. Jede Operation läuft typischerweise in einer Hintergrundaufgabe (eigener
Thread): Sie liest Config und Passwort genau einmal beim Start (Schnappschuss), baut
einen neuen Client und öffnet - falls nötig - eine eigene SQLite-Connection, die sie
vor der Rückkehr schließt (Connections dürfen nicht threadübergreifend genutzt werden).
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from fritz_callhistory import credentials
from fritz_callhistory.config import Config
from fritz_callhistory.db.connection import connect
from fritz_callhistory.db.repository import (
    CallRepository,
    ContactRepository,
    LocalPhonebookRepository,
    PhonebookRepository,
    VoicemailMessageRecord,
    VoicemailRepository,
)
from fritz_callhistory.fritz.client import FritzBoxClient
from fritz_callhistory.fritz.exceptions import FritzBoxAuthError
from fritz_callhistory.sync.phonebook_io import import_from_box
from fritz_callhistory.sync.service import SyncService


@dataclass(frozen=True)
class _Snapshot:
    config: Config
    password: str


class BoxGateway:
    def __init__(
        self,
        config: Config,
        *,
        db_path: Path,
        client_factory: Callable[[str, str, str], FritzBoxClient] = FritzBoxClient,
        get_password: Callable[[str], str | None] = credentials.get_password,
    ) -> None:
        self._config = config
        self._db_path = db_path
        self._client_factory = client_factory
        self._get_password = get_password

    @property
    def config(self) -> Config:
        return self._config

    def apply_config(self, new_config: Config) -> None:
        """Ersetzt die Config (Zugangsdaten oder Einstellungen); laufende Operationen
        behalten ihren Schnappschuss."""
        self._config = new_config

    @property
    def has_credentials(self) -> bool:
        config = self._config
        return bool(config.username and self._get_password(config.username))

    def _snapshot(self) -> _Snapshot:
        config = self._config
        password = self._get_password(config.username) if config.username else None
        if not password:
            raise FritzBoxAuthError("Keine Zugangsdaten gespeichert.")
        return _Snapshot(config, password)

    def _client(self, snapshot: _Snapshot):
        config = snapshot.config
        return self._client_factory(config.address, config.username, snapshot.password)

    @contextmanager
    def _connection(self):
        connection = connect(self._db_path)
        try:
            yield connection
        finally:
            connection.close()

    def sync(self) -> tuple[int, int]:
        snapshot = self._snapshot()
        with self._connection() as connection:
            client = self._client(snapshot)
            service = SyncService(
                client,
                ContactRepository(connection),
                CallRepository(connection),
                PhonebookRepository(connection),
                LocalPhonebookRepository(connection),
                VoicemailRepository(connection),
                connection,
            )
            inserted = service.sync_calls()
            updated = service.sync_phonebook(snapshot.config.resolved_phonebook_ids())
            service.sync_voicemail()
            return inserted, updated

    def list_phonebooks(self) -> list[tuple[int, str]]:
        return self._client(self._snapshot()).phonebooks()

    def import_from_box(self, phonebook_ids: list[int]) -> int:
        snapshot = self._snapshot()
        with self._connection() as connection:
            return import_from_box(
                self._client(snapshot), LocalPhonebookRepository(connection), phonebook_ids
            )

    def dial(self, number: str) -> None:
        self._client(self._snapshot()).dial_number(number)

    def voicemail_audio(self, message: VoicemailMessageRecord) -> bytes:
        client = self._client(self._snapshot())
        audio = client.voicemail_audio(message.box_path)
        box_index = self._resolve_box_index(client, message)
        if box_index is not None:
            client.voicemail_mark_read(message.tam_index, box_index)
        return audio

    def voicemail_mark_read(self, message: VoicemailMessageRecord) -> None:
        client = self._client(self._snapshot())
        box_index = self._resolve_box_index(client, message)
        if box_index is not None:
            client.voicemail_mark_read(message.tam_index, box_index)

    def voicemail_delete(self, message: VoicemailMessageRecord) -> None:
        client = self._client(self._snapshot())
        box_index = self._resolve_box_index(client, message)
        if box_index is not None:
            client.voicemail_delete(message.tam_index, box_index)

    def check_credentials(self, address: str, username: str, password: str) -> None:
        """Prüft noch nicht gespeicherte Zugangsdaten (ignoriert die gespeicherte Config).

        Nur einen Client zu bauen schlägt bei falschem Passwort nicht zuverlässig fehl
        (der Login passiert erst beim ersten authentifizierten SOAP-Aufruf);
        get_calls(num=1) ist dieser Aufruf und prüft nebenbei die Anrufliste-Berechtigung.
        """
        self._client_factory(address, username, password).get_calls(num=1)

    @staticmethod
    def _resolve_box_index(client, message: VoicemailMessageRecord) -> int | None:
        """box_index ist nicht stabil über Löschungen hinweg und wird nicht gespeichert:
        unmittelbar vor Gelesen-Markieren/Löschen per (box_path, message_date) neu
        ermitteln. None, wenn die Nachricht auf der Box nicht mehr existiert."""
        for candidate in client.voicemail_messages(message.tam_index):
            if candidate.path == message.box_path and candidate.date == message.message_date:
                return candidate.box_index
        return None
