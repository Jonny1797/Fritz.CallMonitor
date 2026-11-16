"""Gemeinsame Test-Doubles."""

from __future__ import annotations

from fritz_callhistory.fritz.client import FritzPhonebookContact, VoicemailMessage


class FakeClient:
    """Ersatz für FritzBoxClient; zeichnet alle Aufrufe als (name, args) in `calls_made` auf."""

    def __init__(
        self,
        calls=None,
        phonebooks: dict | None = None,
        voicemail_messages: dict[int, list[VoicemailMessage]] | None = None,
        *,
        phonebook_list: list[tuple[int, str]] | None = None,
        phonebook_contacts_detailed: dict[int, list[FritzPhonebookContact]] | None = None,
        audio: bytes = b"",
    ) -> None:
        self._calls = calls or []
        self._phonebooks = phonebooks or {}
        self._voicemail_messages = voicemail_messages or {}
        self._phonebook_list = phonebook_list or []
        self._contacts_detailed = phonebook_contacts_detailed or {}
        self._audio = audio
        self.calls_made: list[tuple] = []

    def get_calls(self, *, num=None, days=None):
        self.calls_made.append(("get_calls", num, days))
        return self._calls

    def phonebook_ids(self):
        return list(self._phonebooks.keys())

    def phonebook_name_numbers(self, phonebook_id):
        self.calls_made.append(("phonebook_name_numbers", phonebook_id))
        return self._phonebooks[phonebook_id]

    def phonebooks(self):
        self.calls_made.append(("phonebooks",))
        return self._phonebook_list

    def phonebook_contacts_detailed(self, phonebook_id):
        self.calls_made.append(("phonebook_contacts_detailed", phonebook_id))
        return self._contacts_detailed.get(phonebook_id, [])

    def dial_number(self, number):
        self.calls_made.append(("dial_number", number))

    def voicemail_tam_indices(self):
        return list(self._voicemail_messages.keys())

    def voicemail_messages(self, tam_index):
        return self._voicemail_messages[tam_index]

    def voicemail_audio(self, path):
        self.calls_made.append(("voicemail_audio", path))
        return self._audio

    def voicemail_mark_read(self, tam_index, message_index):
        self.calls_made.append(("voicemail_mark_read", tam_index, message_index))

    def voicemail_delete(self, tam_index, message_index):
        self.calls_made.append(("voicemail_delete", tam_index, message_index))


class FakeGateway:
    """Ersatz für BoxGateway in GUI-Tests.

    `has_credentials` ist frei setzbar; jeder Aufruf wird als (name, args) in `calls`
    aufgezeichnet. Ergebnis oder Fehler je Operation über `results` / `errors`;
    `handlers` erlaubt blockierende/berechnende Ersatzfunktionen (z.B. mit threading.Event).
    """

    _DEFAULT_RESULTS = {
        "sync": (0, 0),
        "list_phonebooks": [],
        "import_from_box": 0,
        "voicemail_audio": b"",
    }

    def __init__(
        self,
        config=None,
        *,
        has_credentials: bool = True,
        results: dict | None = None,
        errors: dict | None = None,
        handlers: dict | None = None,
    ) -> None:
        from fritz_callhistory.config import Config

        self.config = config or Config()
        self.has_credentials = has_credentials
        self.results = results or {}
        self.errors = errors or {}
        self.handlers = handlers or {}
        self.calls: list[tuple] = []
        self.applied_configs: list = []

    def apply_config(self, new_config) -> None:
        self.config = new_config
        self.applied_configs.append(new_config)

    def _run(self, name: str, *args):
        self.calls.append((name, *args))
        if name in self.handlers:
            return self.handlers[name](*args)
        if name in self.errors:
            raise self.errors[name]
        return self.results.get(name, self._DEFAULT_RESULTS.get(name))

    def sync(self):
        return self._run("sync")

    def list_phonebooks(self):
        return self._run("list_phonebooks")

    def import_from_box(self, phonebook_ids):
        return self._run("import_from_box", phonebook_ids)

    def dial(self, number):
        return self._run("dial", number)

    def voicemail_audio(self, message):
        return self._run("voicemail_audio", message)

    def voicemail_mark_read(self, message):
        return self._run("voicemail_mark_read", message)

    def voicemail_delete(self, message):
        return self._run("voicemail_delete", message)

    def check_credentials(self, address, username, password):
        return self._run("check_credentials", address, username, password)

    def count(self, name: str) -> int:
        return sum(1 for call in self.calls if call[0] == name)
