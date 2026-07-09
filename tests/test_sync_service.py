from fritzconnection.lib.fritzcall import Call

from fritz_callhistory.db.repository import (
    CallRepository,
    ContactRepository,
    LocalPhonebookRepository,
    PhonebookRepository,
    VoicemailRepository,
)
from fritz_callhistory.fritz.client import VoicemailMessage
from fritz_callhistory.sync.service import SyncService, resolve_contact_names


def _make_call(
    *,
    call_type: int,
    caller_number: str | None = None,
    called_number: str | None = None,
    date: str = "01.06.26 10:00",
    duration: str = "0:05",
    name: str | None = None,
    call_id: int | None = None,
) -> Call:
    call = Call()
    call.Id = call_id
    call.Type = call_type
    call.CallerNumber = caller_number
    call.CalledNumber = called_number
    call.Caller = caller_number
    call.Called = called_number
    call.Date = date
    call.Duration = duration
    call.Name = name
    call.Port = "1"
    call.Device = "Fritz!Fon"
    return call


class FakeClient:
    def __init__(
        self,
        calls: list[Call] | None = None,
        phonebooks: dict | None = None,
        voicemail_messages: dict[int, list[VoicemailMessage]] | None = None,
    ) -> None:
        self._calls = calls or []
        self._phonebooks = phonebooks or {}
        self._voicemail_messages = voicemail_messages or {}

    def get_calls(self, *, days=None):
        return self._calls

    def phonebook_ids(self):
        return list(self._phonebooks.keys())

    def phonebook_name_numbers(self, phonebook_id):
        return self._phonebooks[phonebook_id]

    def voicemail_tam_indices(self):
        return list(self._voicemail_messages.keys())

    def voicemail_messages(self, tam_index):
        return self._voicemail_messages[tam_index]


def _service(connection, calls=None, phonebooks=None, voicemail_messages=None):
    return SyncService(
        FakeClient(calls, phonebooks, voicemail_messages),
        ContactRepository(connection),
        CallRepository(connection),
        PhonebookRepository(connection),
        LocalPhonebookRepository(connection),
        VoicemailRepository(connection),
    )


def _make_voicemail_message(
    *,
    tam_index: int = 0,
    box_index: int = 0,
    caller_number: str | None = "0171 2345678",
    called_number: str | None = "06898123456",
    date: str = "2026-06-01T10:00:00",
    duration_seconds: int | None = 4,
    name: str | None = None,
    path: str = "/download.lua?path=/data/tam/rec/rec.0.000",
    is_new: bool = True,
) -> VoicemailMessage:
    return VoicemailMessage(
        tam_index=tam_index,
        box_index=box_index,
        caller_number=caller_number,
        called_number=called_number,
        date=date,
        duration_seconds=duration_seconds,
        name=name,
        path=path,
        is_new=is_new,
    )


def test_sync_outgoing_call_groups_by_called_number(connection):
    call = _make_call(call_type=3, called_number="0171 2345678")
    service = _service(connection, [call])

    inserted = service.sync_calls()

    assert inserted == 1
    contacts = ContactRepository(connection).search("")
    assert len(contacts) == 1
    assert contacts[0].primary_number == "+491712345678"
    assert contacts[0].is_anonymous is False


def test_sync_incoming_call_groups_by_caller_number(connection):
    call = _make_call(call_type=1, caller_number="030 1234567", name="Max Mustermann")
    service = _service(connection, [call])

    service.sync_calls()

    contacts = ContactRepository(connection).search("")
    assert contacts[0].primary_number == "+49301234567"


def test_sync_missed_call_without_duration(connection):
    call = _make_call(call_type=2, caller_number="030 1234567", duration="")
    service = _service(connection, [call])

    service.sync_calls()

    contacts = ContactRepository(connection).search("")
    calls = CallRepository(connection).for_contact(contacts[0].id)
    assert calls[0].duration_seconds is None


def test_sync_anonymous_call_has_no_number(connection):
    call = _make_call(call_type=1, caller_number=None)
    service = _service(connection, [call])

    service.sync_calls()

    contacts = ContactRepository(connection).search("")
    assert contacts[0].is_anonymous is True


def test_sync_is_idempotent_on_repeated_run(connection):
    call = _make_call(call_type=1, caller_number="030 1234567")
    service = _service(connection, [call])

    first = service.sync_calls()
    second = service.sync_calls()

    assert first == 1
    assert second == 0
    contacts = ContactRepository(connection).search("")
    assert len(CallRepository(connection).for_contact(contacts[0].id)) == 1


def test_sync_two_calls_same_contact_are_grouped(connection):
    calls = [
        _make_call(call_type=1, caller_number="030 1234567", date="01.06.26 10:00"),
        _make_call(call_type=1, caller_number="+49 30 1234567", date="02.06.26 10:00"),
    ]
    service = _service(connection, calls)

    inserted = service.sync_calls()

    assert inserted == 2
    contacts = ContactRepository(connection).search("")
    assert len(contacts) == 1
    assert len(CallRepository(connection).for_contact(contacts[0].id)) == 2


def test_sync_phonebook_resolves_display_name_for_existing_contact(connection):
    call = _make_call(call_type=1, caller_number="030 1234567")
    phonebooks = {0: [("Max Mustermann", ["030 1234567", "0171 2345678"])]}
    service = _service(connection, [call], phonebooks)
    service.sync_calls()

    updated = service.sync_phonebook()

    assert updated == 1
    contact = ContactRepository(connection).search("")[0]
    assert contact.display_name == "Max Mustermann"


def test_sync_phonebook_search_by_name_finds_contact(connection):
    call = _make_call(call_type=1, caller_number="030 1234567")
    phonebooks = {0: [("Max Mustermann", ["030 1234567"])]}
    service = _service(connection, [call], phonebooks)
    service.sync_calls()
    service.sync_phonebook()

    results = ContactRepository(connection).search("Mustermann")

    assert len(results) == 1
    assert results[0].primary_number == "+49301234567"


def test_sync_phonebook_without_matching_contact_updates_nothing(connection):
    phonebooks = {0: [("Max Mustermann", ["030 1234567"])]}
    service = _service(connection, phonebooks=phonebooks)

    updated = service.sync_phonebook()

    assert updated == 0


def test_sync_phonebook_rerun_replaces_stale_entries(connection):
    call = _make_call(call_type=1, caller_number="030 1234567")
    service = _service(connection, [call], {0: [("Alter Name", ["030 1234567"])]})
    service.sync_calls()
    service.sync_phonebook()

    service_updated = _service(connection, phonebooks={0: [("Neuer Name", ["030 1234567"])]})
    updated = service_updated.sync_phonebook()

    assert updated == 1
    contact = ContactRepository(connection).search("")[0]
    assert contact.display_name == "Neuer Name"


def test_sync_calls_stores_box_call_id_for_ordering_tiebreak(connection):
    call = _make_call(call_type=1, caller_number="030 1234567", call_id=42)
    service = _service(connection, [call])
    service.sync_calls()

    contact = ContactRepository(connection).search("")[0]
    records = CallRepository(connection).for_contact(contact.id)

    assert records[0].box_call_id == 42


def test_sync_calls_replaces_placeholder_device_with_none(connection):
    call = _make_call(call_type=10, caller_number="030 1234567")
    call.Device = "-1"
    service = _service(connection, [call])
    service.sync_calls()

    contact = ContactRepository(connection).search("")[0]
    records = CallRepository(connection).for_contact(contact.id)

    assert records[0].device is None


def test_sync_calls_keeps_real_device_value(connection):
    call = _make_call(call_type=1, caller_number="030 1234567")
    call.Device = "Fritz!Fon"
    service = _service(connection, [call])
    service.sync_calls()

    contact = ContactRepository(connection).search("")[0]
    records = CallRepository(connection).for_contact(contact.id)

    assert records[0].device == "Fritz!Fon"


def test_resolve_contact_names_prefers_local_phonebook_over_box_cache(connection):
    call = _make_call(call_type=1, caller_number="030 1234567")
    service = _service(connection, [call], {0: [("Box-Name", ["030 1234567"])]})
    service.sync_calls()
    service.sync_phonebook()

    local_phonebook = LocalPhonebookRepository(connection)
    local_phonebook.create(
        display_name="Lokaler Name",
        notes=None,
        numbers=[("030 1234567", "+49301234567", "home", False)],
    )

    updated = resolve_contact_names(
        ContactRepository(connection), PhonebookRepository(connection), local_phonebook
    )

    assert updated == 1
    contact = ContactRepository(connection).search("")[0]
    assert contact.display_name == "Lokaler Name"


def test_sync_voicemail_inserts_new_messages(connection):
    message = _make_voicemail_message()
    service = _service(connection, voicemail_messages={0: [message]})

    inserted = service.sync_voicemail()

    assert inserted == 1
    messages = VoicemailRepository(connection).list_messages()
    assert len(messages) == 1
    assert messages[0].box_path == message.path
    assert messages[0].is_new is True


def test_sync_voicemail_is_idempotent(connection):
    message = _make_voicemail_message()
    service = _service(connection, voicemail_messages={0: [message]})
    service.sync_voicemail()

    inserted = service.sync_voicemail()

    assert inserted == 0
    assert len(VoicemailRepository(connection).list_messages()) == 1


def test_sync_voicemail_refreshes_is_new(connection):
    message = _make_voicemail_message(is_new=True)
    service = _service(connection, voicemail_messages={0: [message]})
    service.sync_voicemail()

    heard_message = _make_voicemail_message(is_new=False)
    service_after_heard = _service(connection, voicemail_messages={0: [heard_message]})
    service_after_heard.sync_voicemail()

    all_messages = connection.execute("SELECT * FROM voicemail_messages").fetchall()
    assert len(all_messages) == 1
    assert bool(all_messages[0]["is_new"]) is False


def test_sync_voicemail_prunes_messages_deleted_on_box(connection):
    message = _make_voicemail_message()
    service = _service(connection, voicemail_messages={0: [message]})
    service.sync_voicemail()
    assert len(VoicemailRepository(connection).list_messages()) == 1

    # Same TAM slot queried again, but the box no longer returns the message
    # (e.g. deleted via a handset) - the local row must be pruned.
    service_after_delete = _service(connection, voicemail_messages={0: []})
    service_after_delete.sync_voicemail()

    assert VoicemailRepository(connection).list_messages() == []


def test_sync_voicemail_does_not_prune_slots_that_were_not_queried(connection):
    message = _make_voicemail_message(tam_index=0)
    service = _service(connection, voicemail_messages={0: [message]})
    service.sync_voicemail()

    # A later sync where slot 0 is disabled (not returned by
    # voicemail_tam_indices() at all) must leave its messages untouched.
    service_no_slots = _service(connection, voicemail_messages={})
    service_no_slots.sync_voicemail()

    assert len(VoicemailRepository(connection).list_messages()) == 1
