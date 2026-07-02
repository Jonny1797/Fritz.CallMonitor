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


def test_find_by_number_returns_matching_contact(connection):
    contacts = ContactRepository(connection)
    contact_id = contacts.upsert("+491234567")
    contacts.set_display_name(contact_id, "Max Mustermann")
    contacts.upsert("+499876543")

    found = contacts.find_by_number("+491234567")

    assert found is not None
    assert found.id == contact_id
    assert found.display_name == "Max Mustermann"


def test_find_by_number_returns_none_when_missing(connection):
    contacts = ContactRepository(connection)
    assert contacts.find_by_number("+491234567") is None


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


def _insert_call(calls, *, contact_id, call_date, call_type=1, duration_seconds=0):
    calls.insert(
        contact_id=contact_id,
        call_type=call_type,
        caller_number="+491234567",
        called_number=None,
        port="1",
        device="Fritz!Fon",
        call_date=call_date,
        duration_seconds=duration_seconds,
        raw_name=None,
    )


def test_all_calls_returns_calls_with_contact_info(connection):
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_id = contacts.upsert("+491234567")
    contacts.set_display_name(contact_id, "Max Mustermann")
    _insert_call(calls, contact_id=contact_id, call_date="2026-06-01T10:00:00")

    results = calls.all_calls()

    assert len(results) == 1
    assert results[0].contact_display_name == "Max Mustermann"
    assert results[0].contact_primary_number == "+491234567"
    assert results[0].contact_is_anonymous is False


def test_all_calls_ordered_newest_first_across_contacts(connection):
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_a = contacts.upsert("+491111111")
    contact_b = contacts.upsert("+492222222")
    _insert_call(calls, contact_id=contact_a, call_date="2026-06-01T10:00:00")
    _insert_call(calls, contact_id=contact_b, call_date="2026-06-03T10:00:00")
    _insert_call(calls, contact_id=contact_a, call_date="2026-06-02T10:00:00")

    results = calls.all_calls()

    assert [r.call_date for r in results] == [
        "2026-06-03T10:00:00",
        "2026-06-02T10:00:00",
        "2026-06-01T10:00:00",
    ]


def test_all_calls_includes_anonymous_contact(connection):
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_id = contacts.upsert("anonymous", is_anonymous=True)
    _insert_call(calls, contact_id=contact_id, call_date="2026-06-01T10:00:00")

    results = calls.all_calls()

    assert results[0].contact_is_anonymous is True
    assert results[0].contact_display_name is None


def test_all_calls_filters_by_date_from_inclusive(connection):
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_id = contacts.upsert("+491234567")
    _insert_call(calls, contact_id=contact_id, call_date="2026-06-01T00:00:00")

    results = calls.all_calls(date_from="2026-06-01T00:00:00")

    assert len(results) == 1


def test_all_calls_filters_by_date_to_inclusive(connection):
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_id = contacts.upsert("+491234567")
    _insert_call(calls, contact_id=contact_id, call_date="2026-06-01T23:59:59")

    results = calls.all_calls(date_to="2026-06-01T23:59:59")

    assert len(results) == 1


def test_all_calls_excludes_calls_outside_range(connection):
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_id = contacts.upsert("+491234567")
    _insert_call(calls, contact_id=contact_id, call_date="2026-05-31T23:59:59")
    _insert_call(calls, contact_id=contact_id, call_date="2026-06-01T12:00:00")
    _insert_call(calls, contact_id=contact_id, call_date="2026-06-03T00:00:00")

    results = calls.all_calls(date_from="2026-06-01T00:00:00", date_to="2026-06-02T23:59:59")

    assert [r.call_date for r in results] == ["2026-06-01T12:00:00"]


def test_all_calls_returns_everything_when_no_filter_given(connection):
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_id = contacts.upsert("+491234567")
    _insert_call(calls, contact_id=contact_id, call_date="2026-01-01T00:00:00")
    _insert_call(calls, contact_id=contact_id, call_date="2026-12-31T23:59:59")

    results = calls.all_calls()

    assert len(results) == 2


def test_all_calls_filters_by_call_types_single(connection):
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_id = contacts.upsert("+491234567")
    _insert_call(calls, contact_id=contact_id, call_date="2026-06-01T10:00:00", call_type=1)
    _insert_call(calls, contact_id=contact_id, call_date="2026-06-02T10:00:00", call_type=2)
    _insert_call(calls, contact_id=contact_id, call_date="2026-06-03T10:00:00", call_type=3)

    results = calls.all_calls(call_types=[2])

    assert len(results) == 1
    assert results[0].call_type == 2


def test_all_calls_filters_by_call_types_multiple(connection):
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_id = contacts.upsert("+491234567")
    _insert_call(calls, contact_id=contact_id, call_date="2026-06-01T10:00:00", call_type=1)
    _insert_call(calls, contact_id=contact_id, call_date="2026-06-02T10:00:00", call_type=2)
    _insert_call(calls, contact_id=contact_id, call_date="2026-06-03T10:00:00", call_type=10)

    results = calls.all_calls(call_types=[2, 10])

    assert {r.call_type for r in results} == {2, 10}


def test_all_calls_call_types_combined_with_date_from(connection):
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_id = contacts.upsert("+491234567")
    _insert_call(calls, contact_id=contact_id, call_date="2026-06-01T10:00:00", call_type=2)
    _insert_call(calls, contact_id=contact_id, call_date="2026-06-05T10:00:00", call_type=2)

    results = calls.all_calls(date_from="2026-06-03T00:00:00", call_types=[2])

    assert [r.call_date for r in results] == ["2026-06-05T10:00:00"]


def test_all_calls_call_types_none_or_empty_returns_all(connection):
    contacts = ContactRepository(connection)
    calls = CallRepository(connection)
    contact_id = contacts.upsert("+491234567")
    _insert_call(calls, contact_id=contact_id, call_date="2026-06-01T10:00:00", call_type=1)
    _insert_call(calls, contact_id=contact_id, call_date="2026-06-02T10:00:00", call_type=2)

    assert len(calls.all_calls(call_types=None)) == 2
    assert len(calls.all_calls(call_types=[])) == 2


def test_sync_state_roundtrip(connection):
    state = SyncStateRepository(connection)
    assert state.get("last_sync_at") is None
    state.set("last_sync_at", "2026-06-01T10:00:00")
    assert state.get("last_sync_at") == "2026-06-01T10:00:00"
    state.set("last_sync_at", "2026-06-02T10:00:00")
    assert state.get("last_sync_at") == "2026-06-02T10:00:00"
