import sqlite3

from fritz_callhistory.db.repository import (
    CallRepository,
    ContactRepository,
    LocalPhonebookRepository,
    PhonebookRepository,
    VoicemailRepository,
)
from fritz_callhistory.db.schema import migrate
from fritz_callhistory.fritz.client import FritzCallListEntry, VoicemailMessage
from fritz_callhistory.sync.caller_directory import CallerDirectory
from fritz_callhistory.sync.service import SyncService

from .fakes import FakeClient


class _CountingConnection(sqlite3.Connection):
    """sqlite3.Connection kann nicht gemonkeypatcht werden (immutable Builtin-Typ) -
    eine Subklasse per connect()-factory zaehlt echte commit()-Aufrufe mit."""

    commit_count = 0

    def commit(self) -> None:
        self.commit_count += 1
        super().commit()


def _make_call(
    *,
    call_type: int,
    caller_number: str | None = None,
    called_number: str | None = None,
    date: str = "2026-06-01T10:00:00",
    duration: int | None = 5,
    name: str | None = None,
    call_id: int | None = None,
) -> FritzCallListEntry:
    return FritzCallListEntry(
        box_call_id=call_id,
        call_type=call_type,
        caller_number=caller_number,
        called_number=called_number,
        port="1",
        device="Fritz!Fon",
        call_date=date,
        duration_seconds=duration,
        name=name,
    )


def _service(connection, calls=None, phonebooks=None, voicemail_messages=None):
    return SyncService(
        FakeClient(calls, phonebooks, voicemail_messages),
        ContactRepository(connection),
        CallRepository(connection),
        PhonebookRepository(connection),
        LocalPhonebookRepository(connection),
        VoicemailRepository(connection),
        connection,
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
    call = _make_call(call_type=2, caller_number="030 1234567", duration=None)
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


def test_sync_calls_commits_once_for_the_whole_batch():
    connection = sqlite3.connect(":memory:", factory=_CountingConnection)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    migrate(connection)
    try:
        calls = [
            _make_call(call_type=1, caller_number="030 1234567", date="2026-06-01T10:00:00", call_id=1),
            _make_call(call_type=1, caller_number="030 7654321", date="2026-06-01T10:05:00", call_id=2),
            _make_call(call_type=1, caller_number="030 1234567", date="2026-06-01T10:10:00", call_id=3),
        ]
        service = _service(connection, calls)
        commits_before = connection.commit_count

        inserted = service.sync_calls()

        assert inserted == 3
        assert connection.commit_count - commits_before == 1
    finally:
        connection.close()


def test_sync_two_calls_same_contact_are_grouped(connection):
    calls = [
        _make_call(call_type=1, caller_number="030 1234567", date="2026-06-01T10:00:00"),
        _make_call(call_type=1, caller_number="+49 30 1234567", date="2026-06-02T10:00:00"),
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


def test_sync_calls_keeps_real_device_value(connection):
    call = _make_call(call_type=1, caller_number="030 1234567")
    call.device = "Fritz!Fon C6"
    service = _service(connection, [call])
    service.sync_calls()

    contact = ContactRepository(connection).search("")[0]
    records = CallRepository(connection).for_contact(contact.id)

    assert records[0].device == "Fritz!Fon C6"


def test_refresh_names_prefers_local_phonebook_over_box_cache(connection):
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

    updated = _resolve(connection, local_phonebook)

    assert updated == 1
    contact = ContactRepository(connection).search("")[0]
    assert contact.display_name == "Lokaler Name"


def _resolve(connection, local):
    return CallerDirectory(
        ContactRepository(connection), PhonebookRepository(connection), local
    ).refresh_names()


def test_refresh_names_clears_name_after_local_contact_deleted(connection):
    _service(connection, [_make_call(call_type=1, caller_number="030 1234567")]).sync_calls()
    local = LocalPhonebookRepository(connection)
    contact_id = local.create(
        display_name="Lokaler Name",
        notes=None,
        numbers=[("030 1234567", "+49301234567", "home", False)],
    )
    _resolve(connection, local)
    assert ContactRepository(connection).search("")[0].display_name == "Lokaler Name"

    local.delete(contact_id)
    updated = _resolve(connection, local)

    assert updated == 1
    assert ContactRepository(connection).search("")[0].display_name is None


def test_refresh_names_falls_back_to_box_name_after_local_contact_deleted(connection):
    service = _service(
        connection,
        [_make_call(call_type=1, caller_number="030 1234567")],
        {0: [("Box-Name", ["030 1234567"])]},
    )
    service.sync_calls()
    service.sync_phonebook()
    local = LocalPhonebookRepository(connection)
    contact_id = local.create(
        display_name="Lokaler Name",
        notes=None,
        numbers=[("030 1234567", "+49301234567", "home", False)],
    )
    _resolve(connection, local)

    local.delete(contact_id)
    _resolve(connection, local)

    assert ContactRepository(connection).search("")[0].display_name == "Box-Name"


def test_refresh_names_returns_zero_when_nothing_changes(connection):
    _service(connection, [_make_call(call_type=1, caller_number="030 1234567")]).sync_calls()

    updated = _resolve(connection, LocalPhonebookRepository(connection))

    assert updated == 0
    assert ContactRepository(connection).search("")[0].display_name is None


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
