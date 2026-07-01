from fritz_callhistory.db.repository import CallRepository, ContactRepository, SyncStateRepository


def test_upsert_contact_is_idempotent(connection):
    contacts = ContactRepository(connection)
    id_first = contacts.upsert("+491234567")
    id_second = contacts.upsert("+491234567")
    assert id_first == id_second


def test_contact_search_matches_name_and_number(connection):
    contacts = ContactRepository(connection)
    contact_id = contacts.upsert("+491234567")
    contacts.set_display_name(contact_id, "Max Mustermann")

    assert [c.id for c in contacts.search("Mustermann")] == [contact_id]
    assert [c.id for c in contacts.search("1234567")] == [contact_id]
    assert contacts.search("does-not-exist") == []


def test_call_insert_dedupes_on_natural_key(connection):
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_id = contacts.upsert("+491234567")

    call_kwargs = dict(
        contact_id=contact_id,
        call_type=1,
        caller_number="+491234567",
        called_number="+4900000000",
        port="1",
        device="Fritz!Fon",
        call_date="2026-06-01T10:00:00",
        duration_seconds=42,
        raw_name="Max Mustermann",
    )

    assert calls.insert(**call_kwargs) is True
    # Erneuter Sync desselben Anrufs darf keinen Duplikat-Eintrag erzeugen.
    assert calls.insert(**call_kwargs) is False

    records = calls.for_contact(contact_id)
    assert len(records) == 1
    assert records[0].duration_seconds == 42


def test_calls_for_contact_ordered_newest_first(connection):
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_id = contacts.upsert("+491234567")

    for i, date in enumerate(["2026-06-01T10:00:00", "2026-06-03T10:00:00", "2026-06-02T10:00:00"]):
        calls.insert(
            contact_id=contact_id,
            call_type=1,
            caller_number="+491234567",
            called_number=None,
            port=None,
            device=None,
            call_date=date,
            duration_seconds=i,
            raw_name=None,
        )

    records = calls.for_contact(contact_id)
    assert [r.call_date for r in records] == [
        "2026-06-03T10:00:00",
        "2026-06-02T10:00:00",
        "2026-06-01T10:00:00",
    ]


def test_sync_state_roundtrip(connection):
    state = SyncStateRepository(connection)
    assert state.get("last_sync_at") is None
    state.set("last_sync_at", "2026-06-01T10:00:00")
    assert state.get("last_sync_at") == "2026-06-01T10:00:00"
    state.set("last_sync_at", "2026-06-02T10:00:00")
    assert state.get("last_sync_at") == "2026-06-02T10:00:00"
