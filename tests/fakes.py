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
